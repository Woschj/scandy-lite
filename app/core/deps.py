"""
Zentrale Auth-/Scoping-Dependencies.

Berechtigungsmodell: Admin ist ein globales Flag (User.is_admin) - voller
Zugriff überall, immer auf alle Abteilungen gleichzeitig. Für alle anderen
bestimmt sich die Rolle PRO ABTEILUNG über UserDepartmentRole (app/core/access.py)
- eine Person kann in mehreren Abteilungen unterschiedliche Rollen haben.

Es gibt bewusst KEIN "aktuell aktive Abteilung"-Konzept (keinen Umschalter,
kein Cookie) mehr: Listen zeigen immer alles, wozu der jeweilige User Zugriff
hat (siehe app.core.access.get_visible_department_ids), mit einem Abteilungs-
Badge pro Karte, falls mehrere Abteilungen gemischt sichtbar sind. Beim
Anlegen eines neuen Gegenstands/Mitarbeiters/etc. ist die Abteilung ein
normales Formularfeld (aus den Abteilungen, in denen der User Mitarbeiter-
Rolle hat) - kein vorher zu wählender Kontext. Bearbeiten braucht ohnehin nie
einen Kontext, weil der Datensatz seine Abteilung schon kennt.

Web-App-typisches Pattern (statt 401-JSON): fehlt/verfällt die Session,
wird auf /auth/login umgeleitet. Der `RedirectToLogin`-Marker wird in
app/main.py per Exception-Handler in ein echtes Redirect übersetzt.
"""
import uuid

from fastapi import Depends, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_department_roles
from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import decode_access_token, verify_csrf_token
from app.models.common import UserRole
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
    if not user.is_admin:
        raise Forbidden()
    return user


async def require_staff(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Grobes Gate: hat dieser User IRGENDWO eine Mitarbeiter-Rolle (oder ist
    Admin)? Blockt reine Nutzer-Accounts komplett aus. Die feingranulare Prüfung
    (Mitarbeiter-Rolle SPEZIFISCH für die betroffene Abteilung) passiert danach
    innerhalb der jeweiligen Route über app.core.access.is_staff_in_department,
    sobald die konkrete Abteilung des Gegenstands/Datensatzes bekannt ist."""
    if user.is_admin:
        return user
    from app.models.user_department_role import UserDepartmentRole
    result = await session.exec(
        select(UserDepartmentRole).where(
            UserDepartmentRole.user_id == user.id, UserDepartmentRole.role == UserRole.MITARBEITER
        )
    )
    if not result.first():
        raise Forbidden()
    return user


async def verify_csrf(request: Request) -> None:
    """CSRF-Schutz für mutierende Formulare: das Token aus dem versteckten
    `csrf_token`-Feld muss zum aktuellen Session-Cookie passen (siehe
    app.core.security.generate_csrf_token). `await request.form()` wird von
    Starlette pro Request gecacht - die spätere `Form(...)`-Deklaration im
    Route-Handler liest dieselbe gecachte FormData, der Body wird also nicht
    doppelt geparst.

    Nur für POST relevant; als Router-Dependency eingebunden wirkt das auch
    auf GET-Routen desselben Routers, dort aber wirkungslos (early return).
    Bewusst NICHT im auth-Router: vor dem Login existiert noch kein Session-
    Cookie, aus dem sich ein Token ableiten ließe (siehe README/Statusdoc)."""
    if request.method != "POST":
        return
    form = await request.form()
    token = form.get("csrf_token", "")
    session_value = request.cookies.get(settings.SESSION_COOKIE_NAME, "")
    if not verify_csrf_token(str(token), session_value):
        raise Forbidden()


async def populate_nav_context(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Schreibt has_any_staff_role nach request.state, von wo aus der Template-
    Context-Processor (app/core/templating.py) es automatisch für JEDES
    Rendering aufgreift - für die Nav (Scannen/Mitarbeiter/Historie ein-/
    ausblenden), ohne dass jede Route das einzeln berechnen müsste."""
    if user.is_admin:
        request.state.has_any_staff_role = True
        return
    roles = await get_department_roles(session, user)
    request.state.has_any_staff_role = any(r.role == UserRole.MITARBEITER for r in roles)
