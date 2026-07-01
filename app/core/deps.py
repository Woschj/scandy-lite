"""
Zentrale Auth-/Scoping-Dependencies.

Web-App-typisches Pattern (statt 401-JSON): fehlt/verfällt die Session,
wird auf /auth/login umgeleitet. Der `RedirectToLogin`-Marker wird in
app/main.py per Exception-Handler in ein echtes Redirect übersetzt.
"""
import uuid

from fastapi import Depends, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import decode_access_token
from app.models.common import UserRole
from app.models.department import Department
from app.models.user import User

settings = get_settings()


class RedirectToLogin(Exception):
    """Wird geworfen, wenn kein gültiger User ermittelt werden kann."""


class Forbidden(Exception):
    """Eingeloggt, aber keine Berechtigung für diese Aktion/Seite."""


async def get_current_user(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> User:
    token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not token:
        raise RedirectToLogin()

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise RedirectToLogin()

    try:
        user_id = uuid.UUID(payload["sub"])
    except ValueError:
        raise RedirectToLogin()

    user = await session.get(User, user_id)
    if not user or not user.is_active:
        raise RedirectToLogin()

    return user


async def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.ADMIN:
        raise Forbidden()
    return user


async def get_current_department(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Department | None:
    """Mitarbeiter sind fest auf ihre Abteilung gescoped.
    Admins sehen standardmäßig ihre eigene (falls gesetzt) und können
    über ?department=<code> in eine andere wechseln (Abteilungs-Switcher im UI)."""
    if user.role == UserRole.ADMIN:
        code = request.query_params.get("department")
        if code:
            result = await session.exec(select(Department).where(Department.code == code))
            dept = result.first()
            if dept:
                return dept
        if user.department_id:
            return await session.get(Department, user.department_id)
        return None  # Admin ohne gewählte Abteilung -> Übersicht über alle

    if not user.department_id:
        raise Forbidden()  # Mitarbeiter ohne Abteilung ist ein Datenfehler, kein Edge-Case zum Stillschweigen
    return await session.get(Department, user.department_id)
