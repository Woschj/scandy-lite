"""
SSO-Login-Einstieg + Callback (OpenID Connect, siehe app/core/oidc.py). Nur
aktiv, wenn settings.oidc_enabled - beide Routen antworten sonst mit 403.

Bewusst OHNE populate_nav_context als Router-Dependency (anders als die
meisten anderen Router): das würde intern get_current_user aufrufen, das
OHNE gültiges Session-Cookie sofort auf /auth/login umleitet - genau das
Cookie, das diese Route hier erst noch ausstellen soll. Gleiches Prinzip wie
app.routers.auth (auch ohne diese Dependency).

Erstanmeldung einer bislang unbekannten Person (kein passender external_id)
legt automatisch ein Konto an, aber GESPERRT (approved_at NULL) - ein Admin
muss es erst freischalten (app.routers.admin_settings, Abteilung + Rolle
werden dabei festgelegt).
"""
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.deps import Forbidden
from app.core.oidc import oauth, unique_username_from_claims
from app.core.responses import redirect_with_query
from app.core.security import create_access_token, set_session_cookie
from app.core.templating import templates
from app.models.common import AuthSource
from app.models.user import User

router = APIRouter(prefix="/auth/oidc", tags=["oidc"])
settings = get_settings()
logger = logging.getLogger("scandy-lite")


def _require_enabled() -> None:
    if not settings.oidc_enabled:
        raise Forbidden()


@router.get("/login")
async def oidc_login(request: Request):
    _require_enabled()
    redirect_uri = str(request.url_for("oidc_callback"))
    return await oauth.oidc.authorize_redirect(request, redirect_uri)


@router.get("/callback", name="oidc_callback")
async def oidc_callback(request: Request, session: AsyncSession = Depends(get_session)):
    _require_enabled()

    try:
        token = await oauth.oidc.authorize_access_token(request)
    except Exception:
        # Bewusst breit: Netzwerkfehler, abgelaufener/gefälschter state,
        # JWKS-Probleme etc. sollen alle gleich enden (freundliche Meldung,
        # kein 500) statt jede Fehlerklasse einzeln behandeln zu müssen -
        # dieselbe Grundhaltung wie bei den IntegrityError-Fängern in
        # app/routers/scan.py, nur breiter, weil hier ein externer Dienst
        # (statt nur die eigene DB) beteiligt ist.
        logger.warning("OIDC-Callback fehlgeschlagen (Token-Austausch/State-Prüfung)", exc_info=True)
        return redirect_with_query("/auth/login", error="SSO-Anmeldung fehlgeschlagen. Bitte erneut versuchen.")

    claims = token.get("userinfo") or await oauth.oidc.userinfo(token=token)
    sub = claims.get("sub") if claims else None
    if not sub:
        return redirect_with_query("/auth/login", error="SSO-Anmeldung fehlgeschlagen (keine Nutzerkennung erhalten).")

    result = await session.exec(select(User).where(User.external_id == sub, User.auth_source == AuthSource.SSO))
    user = result.first()

    if not user:
        username = await unique_username_from_claims(session, claims, sub)
        user = User(
            username=username,
            email=claims.get("email"),
            first_name=claims.get("given_name"),
            last_name=claims.get("family_name"),
            auth_source=AuthSource.SSO,
            external_id=sub,
            is_active=False,
            approved_at=None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

    if user.deleted_at is not None:
        return redirect_with_query("/auth/login", error="Konto ist nicht mehr verfügbar.")

    if user.approved_at is None:
        return templates.TemplateResponse(request, "auth/oidc_pending.html", {"pending_user": user})

    if not user.is_active:
        return redirect_with_query("/auth/login", error="Konto ist deaktiviert - bitte an einen Admin wenden.")

    access_token = create_access_token(subject=str(user.id), extra_claims={"is_admin": user.is_admin})
    response = RedirectResponse(url="/", status_code=303)
    set_session_cookie(response, access_token)
    return response
