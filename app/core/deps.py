"""
Zentrale Auth-/Scoping-Dependencies.

Berechtigungsmodell: Admin ist ein globales Flag (User.is_admin) - voller
Zugriff überall. Für alle anderen bestimmt sich die Rolle PRO ABTEILUNG
über UserDepartmentRole (app/core/access.py) - eine Person kann in
mehreren Abteilungen unterschiedliche Rollen haben.

Web-App-typisches Pattern (statt 401-JSON): fehlt/verfällt die Session,
wird auf /auth/login umgeleitet. Der `RedirectToLogin`-Marker wird in
app/main.py per Exception-Handler in ein echtes Redirect übersetzt.
"""
import uuid

from fastapi import Depends, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_accessible_departments, get_department_roles
from app.core.config import get_settings
from app.core.database import get_session
from app.core.security import decode_access_token
from app.models.common import UserRole
from app.models.department import Department
from app.models.user import User

settings = get_settings()

# Sentinel statt leerem String: ein Cookie mit leerem Value ist technisch
# erlaubt, aber unnötig fragil (manche Proxys/Browser normalisieren das weg).
# Damit "Alle Abteilungen" als bewusste Wahl über Seitenwechsel hinweg
# bestehen bleibt (nicht nur "kein Cookie" = Fallback auf Default), braucht
# es einen eigenen erkennbaren Wert.
ALL_DEPARTMENTS_SENTINEL = "__all__"
DEPARTMENT_COOKIE_NAME = "scandy_active_department"
DEPARTMENT_COOKIE_MAX_AGE = 60 * 60 * 24 * 30


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


async def populate_switchable_departments(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Schreibt die für DIESEN User wechselbaren Abteilungen nach request.state,
    von wo aus sie der Template-Context-Processor (app/core/templating.py)
    automatisch für JEDES Rendering aufgreift. Admin sieht alle aktiven
    Abteilungen; alle anderen nur die, in denen sie überhaupt eine Rolle haben -
    und auch nur, wenn es mehr als eine ist (sonst gibt's nichts zu wechseln).

    Schreibt außerdem has_any_staff_role - ob dieser User IRGENDWO Mitarbeiter
    ist (oder Admin) - für die Nav (Scannen/Mitarbeiter/Historie ein-/ausblenden),
    ohne dass jede Route das einzeln berechnen müsste."""
    accessible = await get_accessible_departments(session, user)
    if user.is_admin:
        request.state.all_departments = accessible
        request.state.has_any_staff_role = True
    else:
        request.state.all_departments = accessible if len(accessible) > 1 else None
        roles = await get_department_roles(session, user)
        request.state.has_any_staff_role = any(r.role == UserRole.MITARBEITER for r in roles)


async def get_current_department(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Department | None:
    """Ermittelt die aktuell aktive Abteilung für diesen Request.

    - Admin: Switcher über ALLE Abteilungen, Default "Alle Abteilungen" (None).
    - Alle anderen: Switcher über die Abteilungen, in denen sie eine Rolle haben.
      Genau eine -> die wird direkt verwendet (kein Switcher nötig). Mehrere ->
      Switcher wie beim Admin, aber auf die eigenen Abteilungen beschränkt,
      "Alle Abteilungen" bedeutet hier "alle MEINE Abteilungen", nicht
      systemweit alle - das übernehmen die Routen über
      app.core.access.get_visible_department_ids.
    - Keine einzige Abteilung -> None, nichts sichtbar/bearbeitbar.

    Die Wahl wird zusätzlich in einem (an die User-ID gebundenen) Cookie
    gemerkt, damit sie über normale Navigations-Links (die den Query-Param
    nicht mitschleppen) hinweg bestehen bleibt. Das Cookie wird hier nur in
    request.state vorgemerkt, nicht direkt gesetzt - siehe
    department_cookie_middleware in app/main.py für den Grund.
    """
    accessible = await get_accessible_departments(session, user)
    accessible_by_code = {d.code: d for d in accessible}

    if not user.is_admin and len(accessible) <= 1:
        # Einfacher Fall: keine oder genau eine Abteilung -> kein Switcher nötig
        return accessible[0] if accessible else None

    # 1) Explizite Wahl über den Dropdown in diesem Request?
    if "department" in request.query_params:
        code = request.query_params["department"]
        if not code:
            request.state.department_cookie_value = f"{user.id}:{ALL_DEPARTMENTS_SENTINEL}"
            return None  # bewusst "Alle (meine) Abteilungen" gewählt
        if code in accessible_by_code:
            request.state.department_cookie_value = f"{user.id}:{code}"
            return accessible_by_code[code]
        # Unbekannter/fremder Code -> ignorieren, unten weiter mit Cookie/Default

    # 2) Keine explizite Wahl in DIESEM Request -> vorherige Wahl aus dem Cookie.
    # Cookie ist an die User-ID gebunden (Format "user_id:wert") - auf einem
    # geteilten Rechner soll ein zweiter Login nicht die Wahl des vorherigen erben.
    cookie_raw = request.cookies.get(DEPARTMENT_COOKIE_NAME)
    cookie_value = None
    if cookie_raw and ":" in cookie_raw:
        cookie_user_id, _, cookie_rest = cookie_raw.partition(":")
        if cookie_user_id == str(user.id):
            cookie_value = cookie_rest

    if cookie_value == ALL_DEPARTMENTS_SENTINEL:
        return None
    if cookie_value and cookie_value in accessible_by_code:
        return accessible_by_code[cookie_value]

    # 3) Kein (gültiges) Cookie -> für Admin Default "Alle Abteilungen",
    # für alle anderen die erste ihrer zugänglichen Abteilungen (deterministisch
    # alphabetisch sortiert von get_accessible_departments).
    if user.is_admin:
        return None
    return accessible[0] if accessible else None
