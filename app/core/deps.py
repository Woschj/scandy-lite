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
    if user.role != UserRole.ADMIN:
        raise Forbidden()
    return user


async def require_staff(user: User = Depends(get_current_user)) -> User:
    """Admin oder Mitarbeiter - Verwaltung (Anlegen/Bearbeiten/Löschen) und
    Ausgabe/Rückgabe (Scan). Die Rolle 'Nutzer' darf ansehen und reservieren,
    aber nicht verwalten oder Ausgaben durchführen."""
    if user.role not in (UserRole.ADMIN, UserRole.MITARBEITER):
        raise Forbidden()
    return user


async def populate_switchable_departments(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Schreibt die wechselbaren Abteilungen (nur für Admins) nach request.state,
    von wo aus sie der Template-Context-Processor (app/core/templating.py)
    automatisch für JEDES Rendering aufgreift. So als Router-weite `dependencies=`
    eingebunden (nicht pro Route einzeln) - kann dadurch nicht mehr vergessen
    werden, wenn eine neue Route dazukommt."""
    if user.role == UserRole.ADMIN:
        result = await session.exec(select(Department).where(Department.is_active == True))  # noqa: E712
        request.state.all_departments = result.all()
    else:
        request.state.all_departments = None


async def get_current_department(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Department | None:
    """Mitarbeiter sind fest auf ihre Abteilung gescoped.
    Admins sehen standardmäßig ihre eigene (falls gesetzt) und können über
    den Nav-Dropdown (?department=<code>) in eine andere wechseln. Die Wahl
    wird zusätzlich in einem Cookie gemerkt, damit sie über normale
    Navigations-Links (die den Query-Param nicht mitschleppen) hinweg
    bestehen bleibt, statt bei jeder neuen Seite auf den Default zurückzufallen.

    Wichtig: das Cookie wird HIER nur in request.state vorgemerkt, nicht
    direkt gesetzt - unsere Routen geben fast durchweg eigene Response-Objekte
    zurück (TemplateResponse/RedirectResponse), wodurch ein hier injiziertes
    Response-Objekt beim Zurückgeben verworfen würde. Die Middleware
    (department_cookie_middleware in app/main.py) setzt das Cookie danach auf
    die tatsächlich ausgehende Antwort, unabhängig davon, wie sie gebaut wurde.
    """
    if user.role == UserRole.NUTZER:
        return None  # Nutzer haben keine einzelne "aktuelle Abteilung" - Sichtbarkeit läuft über Gruppen-Berechtigungen (app/core/access.py)

    if user.role != UserRole.ADMIN:
        if not user.department_id:
            raise Forbidden()  # Mitarbeiter ohne Abteilung ist ein Datenfehler, kein Edge-Case zum Stillschweigen
        return await session.get(Department, user.department_id)

    # 1) Explizite Wahl über den Dropdown in diesem Request?
    if "department" in request.query_params:
        code = request.query_params["department"]
        if not code:
            request.state.department_cookie_value = f"{user.id}:{ALL_DEPARTMENTS_SENTINEL}"
            return None  # Admin hat bewusst "Alle Abteilungen" gewählt

        result = await session.exec(select(Department).where(Department.code == code))
        dept = result.first()
        if dept:
            request.state.department_cookie_value = f"{user.id}:{code}"
            return dept
        # Unbekannter Code im Query-Param -> ignorieren, unten weiter mit Cookie/Default

    # 2) Keine explizite Wahl in DIESEM Request -> vorherige Wahl aus dem Cookie übernehmen.
    # Cookie ist an die User-ID gebunden (Format "user_id:wert") - auf einem geteilten
    # Rechner soll ein zweiter Admin-Login nicht die Abteilungswahl des vorherigen erben.
    cookie_raw = request.cookies.get(DEPARTMENT_COOKIE_NAME)
    cookie_value = None
    if cookie_raw and ":" in cookie_raw:
        cookie_user_id, _, cookie_rest = cookie_raw.partition(":")
        if cookie_user_id == str(user.id):
            cookie_value = cookie_rest

    if cookie_value == ALL_DEPARTMENTS_SENTINEL:
        return None
    if cookie_value:
        result = await session.exec(select(Department).where(Department.code == cookie_value))
        dept = result.first()
        if dept:
            return dept

    # 3) Kein Cookie (erster Besuch) -> eigene Abteilung, sonst "Alle"
    if user.department_id:
        return await session.get(Department, user.department_id)
    return None
