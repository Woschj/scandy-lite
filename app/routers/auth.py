"""
Login-Seite (GET), Login-Verarbeitung (POST) und Logout.

Bewusst als klassisches Formular (kein JSON-API-Login), damit es ohne
JavaScript funktioniert und HTMX es einfach progressiv verbessern kann.
"""
from collections import defaultdict, deque
from time import monotonic

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.deps import verify_csrf
from app.core.email import send_email
from app.core.password_reset import create_reset_token, invalidate_all_tokens_for_user, resolve_reset_token
from app.core.security import create_access_token, hash_password, verify_password
from app.core.templating import templates
from app.models.common import AuthSource
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

# Separater, großzügigerer Bucket für "Passwort vergessen" - verhindert, dass
# die Route zum Mail-Spam (oder zur Username-Enumeration per Timing) missbraucht
# wird, ohne normale Nutzer bei ein paar Versuchen auszusperren.
_MAX_RESET_REQUESTS = 5
_RESET_WINDOW_SECONDS = 300
_reset_requests: dict[str, deque] = defaultdict(deque)


def _is_rate_limited(ip: str) -> bool:
    now = monotonic()
    attempts = _failed_logins[ip]
    while attempts and now - attempts[0] > _WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= _MAX_FAILED_ATTEMPTS


def _register_failed_attempt(ip: str) -> None:
    _failed_logins[ip].append(monotonic())


def _is_reset_rate_limited(ip: str) -> bool:
    now = monotonic()
    attempts = _reset_requests[ip]
    while attempts and now - attempts[0] > _RESET_WINDOW_SECONDS:
        attempts.popleft()
    return len(attempts) >= _MAX_RESET_REQUESTS


def _register_reset_request(ip: str) -> None:
    _reset_requests[ip].append(monotonic())


@router.get("/login")
async def login_page(request: Request, ok: str = ""):
    return templates.TemplateResponse(
        request, "auth/login.html", {"error": None, "ok": ok or None}
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


@router.get("/forgot-password")
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "auth/forgot_password.html", {"error": None, "ok": None})


@router.post("/forgot-password")
async def forgot_password_submit(
    request: Request,
    identifier: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    # Immer dieselbe generische Erfolgsmeldung, unabhängig davon ob ein Konto
    # gefunden wurde - verhindert, dass sich über diese Route erraten lässt,
    # welche Benutzernamen/E-Mail-Adressen existieren (User-Enumeration).
    generic_ok = "Falls ein Konto mit dieser Angabe existiert, wurde eine E-Mail mit einem Link zum Zurücksetzen verschickt."

    client_ip = request.client.host if request.client else "unknown"
    if _is_reset_rate_limited(client_ip):
        return templates.TemplateResponse(
            request,
            "auth/forgot_password.html",
            {"error": "Zu viele Anfragen. Bitte in ein paar Minuten erneut versuchen.", "ok": None},
            status_code=429,
        )
    _register_reset_request(client_ip)

    identifier = identifier.strip()
    result = await session.exec(select(User).where(or_(User.username == identifier, User.email == identifier)))
    user = result.first()

    if user and user.is_active and user.auth_source == AuthSource.LOCAL and user.hashed_password and user.email:
        raw_token = await create_reset_token(session, user)
        await session.commit()
        reset_url = str(request.base_url).rstrip("/") + f"/auth/reset-password/{raw_token}"
        html_body = templates.get_template("email/password_reset.html").render(
            username=user.username, reset_url=reset_url
        )
        await send_email(session, user.email or "", "Scandy-Lite: Passwort zurücksetzen", html_body)

    return templates.TemplateResponse(request, "auth/forgot_password.html", {"error": None, "ok": generic_ok})


@router.get("/reset-password/{token}")
async def reset_password_page(
    request: Request,
    token: str,
    session: AsyncSession = Depends(get_session),
):
    reset_token = await resolve_reset_token(session, token)
    if not reset_token:
        return templates.TemplateResponse(
            request, "auth/reset_password.html", {"error": "invalid", "token": token}
        )
    return templates.TemplateResponse(request, "auth/reset_password.html", {"error": None, "token": token})


@router.post("/reset-password/{token}")
async def reset_password_submit(
    request: Request,
    token: str,
    new_password: str = Form(...),
    session: AsyncSession = Depends(get_session),
):
    reset_token = await resolve_reset_token(session, token)
    if not reset_token:
        return templates.TemplateResponse(
            request, "auth/reset_password.html", {"error": "invalid", "token": token}
        )

    if len(new_password) < 8:
        return templates.TemplateResponse(
            request,
            "auth/reset_password.html",
            {"error": "Passwort zu kurz (min. 8 Zeichen).", "token": token},
        )

    user = await session.get(User, reset_token.user_id)
    if not user or not user.is_active:
        return templates.TemplateResponse(
            request, "auth/reset_password.html", {"error": "invalid", "token": token}
        )

    user.hashed_password = hash_password(new_password)
    session.add(user)
    await invalidate_all_tokens_for_user(session, user.id)
    await session.commit()

    return RedirectResponse(url="/auth/login?ok=Passwort+wurde+geändert.+Bitte+anmelden.", status_code=303)


@router.post("/logout", dependencies=[Depends(verify_csrf)])
async def logout():
    # Bewusst NUR POST (kein GET mehr): ein GET-Logout ist klassisches
    # "Zero-Click-CSRF" - z.B. ein <img src="/auth/logout"> auf einer fremden
    # Seite hätte jeden eingeloggten Besucher kommentarlos ausgeloggt, ganz
    # ohne Interaktion. verify_csrf ist hier gezielt NUR auf diese Route
    # gesetzt (nicht auf den ganzen Router), da /login weiterhin ohne Token
    # funktionieren muss (vor dem Login existiert noch kein Session-Cookie,
    # aus dem sich eins ableiten ließe - siehe app.core.deps.verify_csrf).
    response = RedirectResponse(url="/auth/login", status_code=303)
    response.delete_cookie(settings.SESSION_COOKIE_NAME)
    return response
