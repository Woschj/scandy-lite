"""
Benutzerverwaltung im Admin-Bereich: Login-Konten/Ausweise anlegen,
bearbeiten, deaktivieren, löschen (Soft-Delete, siehe app/core/trash.py),
sowie der Ausweis-Ausdruck für einen beliebigen Benutzer.
"""
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.badge import qr_data_uri
from app.core.database import get_session
from app.core.deps import populate_nav_context, require_admin, verify_csrf
from app.core.email import send_email
from app.core.password_reset import create_reset_token
from app.core.responses import redirect_with_query
from app.core.security import MIN_PASSWORD_LENGTH, hash_password
from app.core.templating import templates
from app.models.common import UserRole, utcnow
from app.models.consumable import ConsumableUsage
from app.models.department import Department
from app.models.lending import Lending
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


@router.post("/users/new")
async def create_user(
    request: Request,
    username: str = Form(..., max_length=100),
    password: str = Form(""),
    first_name: str = Form(..., max_length=100),
    last_name: str = Form(..., max_length=100),
    barcode: str = Form(..., max_length=100),
    home_department_id: uuid.UUID = Form(...),
    initial_role: str = Form(""),
    is_admin: str = Form(""),
    email: str = Form("", max_length=255),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Legt einen Ausweis-Datensatz an, wahlweise mit Login - User und
    Mitarbeiter-Ausweis sind dieselbe Entität (siehe app/models/user.py).

    password ist bewusst optional: leer gelassen bleibt hashed_password NULL
    (reiner Ausweis-Inhaber ohne Login, s. Docstring auf User.hashed_password) -
    für Barcode-Scan (Ausleihe/Rückgabe/Entnahme) wird kein Login gebraucht,
    nur wer sich selbst einloggen soll (Reservieren im Web, Verwalten) braucht
    eins.

    home_department_id ist NUR die organisatorische Heimat des Ausweises (wo
    der Datensatz verwaltet wird) - das gewährt für sich genommen KEINEN
    Zugriff. Deshalb zusätzlich initial_role: optional wird direkt eine
    UserDepartmentRole für dieselbe Abteilung mit angelegt, damit ein neuer
    Login sofort etwas sehen kann (bei einem passwortlosen Ausweis ohne
    Wirkung, da er sich ohnehin nicht einloggen kann). Weitere Abteilungen/
    Rollen bleiben über den 'Zugriff'-Tab verwaltbar."""
    username = username.strip()
    barcode = barcode.strip()
    email = email.strip()

    existing_user = await session.exec(select(User).where(User.username == username))
    if existing_user.first():
        return RedirectResponse(url="/admin/settings?error=Benutzername+bereits+vergeben.#users", status_code=303)
    if password and len(password) < MIN_PASSWORD_LENGTH:
        return RedirectResponse(url=f"/admin/settings?error=Passwort+zu+kurz+(min.+{MIN_PASSWORD_LENGTH}+Zeichen).#users", status_code=303)

    existing_barcode = await session.exec(select(User).where(User.barcode == barcode, User.deleted_at.is_(None)))
    if existing_barcode.first():
        return RedirectResponse(url="/admin/settings?error=Barcode+ist+bereits+vergeben.#users", status_code=303)

    new_user = User(
        username=username,
        email=email or None,
        is_admin=bool(is_admin),
        hashed_password=await run_in_threadpool(hash_password, password) if password else None,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        barcode=barcode,
        department_id=home_department_id,
        approved_at=utcnow(),  # von einem Admin angelegt = implizit freigeschaltet, nie "ausstehend"
    )
    session.add(new_user)
    await session.flush()  # user.id wird für die optionale UserDepartmentRole gebraucht

    if initial_role in {UserRole.MITARBEITER.value, UserRole.NUTZER.value} and not new_user.is_admin:
        session.add(UserDepartmentRole(user_id=new_user.id, department_id=home_department_id, role=UserRole(initial_role)))

    await session.commit()

    # Willkommens-Mail ist optional/best-effort: schlägt der Versand fehl
    # (SMTP nicht konfiguriert, falsche Zugangsdaten, ...), bleibt der Login
    # trotzdem angelegt - nur eine Warnung statt eines harten Fehlers, siehe
    # app.core.email.send_email-Docstring.
    if email:
        raw_token = await create_reset_token(session, new_user)
        await session.commit()
        set_password_url = str(request.base_url).rstrip("/") + f"/auth/reset-password/{raw_token}"
        html_body = templates.get_template("email/welcome.html").render(
            username=new_user.username, set_password_url=set_password_url
        )
        sent = await send_email(session, email, "Willkommen bei Scandy-Lite", html_body)
        if not sent:
            return redirect_with_query(
                "/admin/settings", fragment="users",
                error=f"{username} wurde angelegt, die Willkommens-Mail konnte aber nicht verschickt werden.",
            )

    return RedirectResponse(url="/admin/settings#users", status_code=303)


@router.post("/users/{user_id}/toggle")
async def toggle_user(
    user_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    target = await session.get(User, user_id)
    if target and target.id != user.id:  # sich selbst aussperren verhindern
        target.is_active = not target.is_active
        session.add(target)
        await session.commit()
    return RedirectResponse(url="/admin/settings#users", status_code=303)


@router.get("/users/{user_id}/ausweis")
async def user_badge(
    request: Request,
    user_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Admin-Variante von app.routers.badge.my_badge - Ausweis eines
    BELIEBIGEN Benutzers ansehen/drucken (z.B. um ihn direkt bei der
    Einstellung des Zugangs mit auszudrucken), gleiches Template."""
    result = await session.exec(select(User).where(User.id == user_id).options(selectinload(User.department)))
    target = result.first()
    if not target or target.deleted_at is not None:
        return RedirectResponse(url="/admin/settings#users", status_code=303)
    qr = qr_data_uri(target.barcode) if target.barcode else None
    return templates.TemplateResponse(
        request, "badge.html",
        {"user": user, "target": target, "qr": qr, "back_url": "/admin/settings#users"},
    )


@router.get("/users/{user_id}/edit")
async def edit_user_form(
    request: Request,
    user_id: uuid.UUID,
    error: str = "",
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    target = await session.get(User, user_id)
    if not target or target.deleted_at is not None:
        return RedirectResponse(url="/admin/settings#users", status_code=303)

    departments = (await session.exec(select(Department).order_by(Department.name))).all()

    # Zugriffsrolle pro Abteilung wird seit dieser Änderung direkt hier
    # mitbearbeitet statt auf einem eigenen "Zugriff"-Tab (der lief bei
    # Abteilungswechseln leicht auseinander, siehe CHANGELOG 0.16.1) -
    # dept_id (als String, wie im Formular/Template) -> Rollen-Wert.
    access_roles = {
        str(r.department_id): r.role.value
        for r in (await session.exec(select(UserDepartmentRole).where(UserDepartmentRole.user_id == target.id))).all()
    }

    # Kompakte, chronologische Historie DIESES Benutzers (Ausleihen +
    # Entnahmen gemeinsam sortiert) - einfacheres Merge-Prinzip als
    # app/routers/history.py, weil hier keine Signatur-Gruppierung nötig ist.
    lendings = (
        await session.exec(
            select(Lending).where(Lending.worker_id == target.id).options(selectinload(Lending.item)).order_by(Lending.lent_at.desc()).limit(20)
        )
    ).all()
    usages = (
        await session.exec(
            select(ConsumableUsage)
            .where(ConsumableUsage.worker_id == target.id)
            .options(selectinload(ConsumableUsage.consumable))
            .order_by(ConsumableUsage.used_at.desc())
            .limit(20)
        )
    ).all()
    user_history = sorted(
        [{"timestamp": lend.lent_at, "kind": "lending", "row": lend} for lend in lendings]
        + [{"timestamp": u.used_at, "kind": "usage", "row": u} for u in usages],
        key=lambda e: e["timestamp"], reverse=True,
    )[:20]

    return templates.TemplateResponse(
        request, "admin/user_edit.html",
        {
            "user": user, "target": target, "departments": departments, "error": error,
            "user_history": user_history, "access_roles": access_roles,
        },
    )


@router.post("/users/{user_id}/edit")
async def update_user(
    request: Request,
    user_id: uuid.UUID,
    username: str = Form(...),
    email: str = Form(""),
    new_password: str = Form(""),
    is_admin: str = Form(""),
    first_name: str = Form(...),
    last_name: str = Form(...),
    barcode: str = Form(...),
    department_id: uuid.UUID = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    target = await session.get(User, user_id)
    if not target or target.deleted_at is not None:
        return RedirectResponse(url="/admin/settings#users", status_code=303)

    username = username.strip()
    email = email.strip()
    barcode = barcode.strip()
    if not username:
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=Benutzername+darf+nicht+leer+sein.", status_code=303)
    if not barcode:
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=Barcode+darf+nicht+leer+sein.", status_code=303)

    existing = await session.exec(select(User).where(User.username == username, User.id != user_id))
    if existing.first():
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=Benutzername+bereits+vergeben.", status_code=303)

    barcode_conflict = await session.exec(
        select(User).where(User.barcode == barcode, User.id != user_id, User.deleted_at.is_(None))
    )
    if barcode_conflict.first():
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=Barcode+ist+bereits+vergeben.", status_code=303)

    if new_password and len(new_password) < MIN_PASSWORD_LENGTH:
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=Neues+Passwort+zu+kurz+(min.+{MIN_PASSWORD_LENGTH}+Zeichen).", status_code=303)

    # Sich selbst die Admin-Rechte zu entziehen wäre eine Selbstaussperrung -
    # verhindern, genau wie beim Deaktivieren/Löschen des eigenen Kontos.
    if user_id == user.id and not bool(is_admin):
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=Eigene+Admin-Rechte+können+nicht+selbst+entzogen+werden.", status_code=303)

    target.username = username
    target.email = email or None
    target.is_admin = bool(is_admin)
    target.first_name = first_name.strip()
    target.last_name = last_name.strip()
    target.barcode = barcode
    target.department_id = department_id
    if new_password:
        target.hashed_password = await run_in_threadpool(hash_password, new_password)
    session.add(target)

    # Zugriffsrolle pro Abteilung wird auf DERSELBEN Seite mitgepflegt (kein
    # eigener "Zugriff"-Tab mehr, siehe CHANGELOG 0.16.1/0.17.0) - das
    # Formular schickt ein role_<department_id>-Feld pro Abteilung
    # (Werte: "", "nutzer", "mitarbeiter"). Admin braucht keine Einträge
    # (globaler Zugriff), also bei is_admin alle vorhandenen Rollen entfernen
    # statt sie als bedeutungslose Karteileichen stehen zu lassen.
    form_data = await request.form()
    existing_roles = {
        r.department_id: r
        for r in (await session.exec(select(UserDepartmentRole).where(UserDepartmentRole.user_id == target.id))).all()
    }
    if target.is_admin:
        for role_row in existing_roles.values():
            await session.delete(role_row)
    else:
        all_departments = (await session.exec(select(Department.id))).all()
        for dept_id in all_departments:
            desired = (form_data.get(f"role_{dept_id}") or "").strip()
            current = existing_roles.get(dept_id)
            if desired in {UserRole.NUTZER.value, UserRole.MITARBEITER.value}:
                if current and current.role.value != desired:
                    current.role = UserRole(desired)
                    session.add(current)
                elif not current:
                    session.add(UserDepartmentRole(user_id=target.id, department_id=dept_id, role=UserRole(desired)))
            elif current:
                await session.delete(current)

    await session.commit()
    return RedirectResponse(url="/admin/settings#users", status_code=303)


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Soft-Delete (wie bei Gegenständen/Verbrauchsmaterial) statt hartem
    Löschen - jetzt hängt Ausleih-/Reservierungs-Historie direkt am User
    (Lending.worker_id etc.), die darf nicht zerreißen. Landet im Papierkorb-
    Tab, von dort aus wiederherstellbar oder (mit Blocker-Prüfung auf offene
    Ausleihen/Reservierungen) endgültig löschbar (siehe app/core/trash.py)."""
    if user_id == user.id:
        return RedirectResponse(url="/admin/settings?error=Eigenes+Konto+kann+nicht+gelöscht+werden.#users", status_code=303)

    target = await session.get(User, user_id)
    if target and target.deleted_at is None:
        target.deleted_at = utcnow()
        session.add(target)
        await session.commit()
    return RedirectResponse(url="/admin/settings#users", status_code=303)
