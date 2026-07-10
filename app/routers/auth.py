"""
Login-Seite (GET), Login-Verarbeitung (POST) und Logout.

Bewusst als klassisches Formular (kein JSON-API-Login), damit es ohne
JavaScript funktioniert und HTMX es einfach progressiv verbessern kann.
"""
from collections import defaultdict, deque
from time import monotonic

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import create_access_token, verify_password
from app.core.templating import templates
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

# Simples In-Memory-Rate-Limit gegen Brute-Force: max. N Fehlversuche pro IP
# im Zeitfenster. Bewusst ohne externe Abhängigkeit (Redis etc.) - für ein
# internes Tool mit einem einzelnen App-Container angemessen; bei mehreren
# Replikas müsste das in einen gemeinsamen Store wandern.
_MAX_FAILED_ATTEMPTS = 10
_WINDOW_SECONDS = 300
_failed_logins: dict[str, deque] = defaultdict(deque)


def _is_rate_limited(ip: str) -> bool:
    now = monotonic()
    attempts = _failed_logins[ip]
    while attempts and now - attempts[0] > _WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= _MAX_FAILED_ATTEMPTS


def _register_failed_attempt(ip: str) -> None:
    _failed_logins[ip].append(monotonic())


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(
        request, "auth/login.html", {"error": None}
    )


@router.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    client_ip = request.client.host if request.client else "unknown"
    if _is_rate_limited(client_ip):
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Zu viele Fehlversuche. Bitte in ein paar Minuten erneut versuchen."},
            status_code=429,
        )

    result = await session.exec(select(User).where(User.username == username))
    user = result.first()

    invalid = (
        not user
        or not user.is_active
        or not user.hashed_password  # LDAP/SSO-User haben kein lokales Passwort
        or not verify_password(password, user.hashed_password)
    )
    if invalid:
        _register_failed_attempt(client_ip)
        return templates.TemplateResponse(
            request,
            "auth/login.html",
            {"error": "Benutzername oder Passwort ist falsch."},
            status_code=401,
        )

    token = create_access_token(
        subject=str(user.id),
        extra_claims={"is_admin": user.is_admin},
    )

    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return response


@router.get("/logout")
@router.post("/logout")
async def logout():
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response
