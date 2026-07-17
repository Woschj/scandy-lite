"""
Admin-Einstellungen: Abteilungen anlegen/umbenennen/deaktivieren,
Kategorien-/Standort-Vorschläge und Zusatzfelder pflegen, Benutzer verwalten,
und die Abteilungs-Rollen-Zuordnung (wer darf was in welcher Abteilung).

Bewusst schlank gehalten (ggü. dem Original-Scandy2-Systembereich): kein
Feature-Flags-System, kein Notification-Center - nur die Presets, die die
Formulare tatsächlich brauchen.
"""
import uuid
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.crypto import encrypt_secret
from app.core.database import get_session
from app.core.deps import require_admin, populate_nav_context, verify_csrf
from app.core.email import get_email_settings, send_email
from app.core.password_reset import create_reset_token
from app.core.responses import redirect_with_query
from app.core.security import hash_password
from app.core.templating import templates
from app.core.trash import (
    get_trash_entries,
    purge_consumable,
    purge_department,
    purge_item,
    purge_user,
    restore_consumable,
    restore_item,
    restore_user,
)
from app.models.common import CustomFieldType, UserRole, utcnow
from app.models.consumable import Consumable, ConsumableUsage
from app.models.custom_field import CustomFieldDefinition, CustomFieldValue
from app.models.department import Department
from app.models.email_settings import EmailSettings
from app.models.item import Item
from app.models.lending import Lending
from app.models.preset import Category, Location
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole
from app.version import __version__

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


@router.get("/settings")
async def settings_page(
    request: Request,
    ok: str = "",
    error: str = "",
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    departments = (await session.exec(select(Department).order_by(Department.name))).all()
    categories = (await session.exec(
        select(Category).order_by(Category.department_id, Category.name)
    )).all()
    locations = (await session.exec(
        select(Location).order_by(Location.department_id, Location.name)
    )).all()
    users = (await session.exec(select(User).where(User.deleted_at.is_(None)).order_by(User.username))).all()

    access_result = await session.exec(
        select(UserDepartmentRole)
        .options(selectinload(UserDepartmentRole.user), selectinload(UserDepartmentRole.department))
        .order_by(UserDepartmentRole.department_id)
    )
    all_access = access_result.all()
    # je User gruppiert, damit die Oberfläche "Login X: Rolle in Abteilung Y, Z" anzeigen kann
    access_by_user: dict = {}
    for entry in all_access:
        access_by_user.setdefault(entry.user_id, []).append(entry)

    email_settings = await get_email_settings(session)

    custom_fields_result = await session.exec(select(CustomFieldDefinition).order_by(CustomFieldDefinition.name))
    custom_fields = custom_fields_result.all()

    trash_items, trash_consumables, trash_users = await get_trash_entries(session)

    return templates.TemplateResponse(
        request,
        "admin/settings.html",
        {
            "user": user,
            "departments": departments,
            "categories": categories,
            "locations": locations,
            "users": users,
            "access_by_user": access_by_user,
            "all_access": all_access,
            "email_settings": email_settings,
            "custom_fields": custom_fields,
            "trash_items": trash_items,
            "trash_consumables": trash_consumables,
            "trash_users": trash_users,
            "version": __version__,
            "ok": ok,
            "error": error,
        },
    )


# --- Benutzer ----------------------------------------------------------

@router.post("/users/new")
async def create_user(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    barcode: str = Form(...),
    home_department_id: uuid.UUID = Form(...),
    initial_role: str = Form(""),
    is_admin: str = Form(""),
    email: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Legt einen Login an - User und Mitarbeiter-Ausweis sind dieselbe
    Entität (siehe app/models/user.py), also immer in einem Schritt.

    home_department_id ist NUR die organisatorische Heimat des Ausweises (wo
    der Datensatz verwaltet wird) - das gewährt für sich genommen KEINEN
    Zugriff. Deshalb zusätzlich initial_role: optional wird direkt eine
    UserDepartmentRole für dieselbe Abteilung mit angelegt, damit der neue
    Login sofort etwas sehen kann. Weitere Abteilungen/Rollen bleiben über
    den 'Zugriff'-Tab verwaltbar."""
    username = username.strip()
    barcode = barcode.strip()
    email = email.strip()

    existing_user = await session.exec(select(User).where(User.username == username))
    if existing_user.first():
        return RedirectResponse(url="/admin/settings?error=Benutzername+bereits+vergeben.#users", status_code=303)
    if len(password) < 8:
        return RedirectResponse(url="/admin/settings?error=Passwort+zu+kurz+(min.+8+Zeichen).#users", status_code=303)

    existing_barcode = await session.exec(select(User).where(User.barcode == barcode, User.deleted_at.is_(None)))
    if existing_barcode.first():
        return RedirectResponse(url="/admin/settings?error=Barcode+ist+bereits+vergeben.#users", status_code=303)

    new_user = User(
        username=username,
        email=email or None,
        is_admin=bool(is_admin),
        hashed_password=hash_password(password),
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        barcode=barcode,
        department_id=home_department_id,
    )
    session.add(new_user)
    await session.flush()  # user.id wird für die optionale UserDepartmentRole gebraucht

    if initial_role in ("mitarbeiter", "nutzer") and not new_user.is_admin:
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
        [{"timestamp": l.lent_at, "kind": "lending", "row": l} for l in lendings]
        + [{"timestamp": u.used_at, "kind": "usage", "row": u} for u in usages],
        key=lambda e: e["timestamp"], reverse=True,
    )[:20]

    return templates.TemplateResponse(
        request, "admin/user_edit.html",
        {"user": user, "target": target, "departments": departments, "error": error, "user_history": user_history},
    )


@router.post("/users/{user_id}/edit")
async def update_user(
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

    if new_password and len(new_password) < 8:
        return RedirectResponse(url=f"/admin/users/{user_id}/edit?error=Neues+Passwort+zu+kurz+(min.+8+Zeichen).", status_code=303)

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
        target.hashed_password = hash_password(new_password)
    session.add(target)
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


# --- Abteilungen -----------------------------------------------------------

@router.post("/departments/new")
async def create_department(
    code: str = Form(...),
    name: str = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(select(Department).where(Department.code == code))
    if not result.first():
        session.add(Department(code=code.strip().lower(), name=name.strip()))
        await session.commit()
    return RedirectResponse(url="/admin/settings#departments", status_code=303)


@router.post("/departments/{department_id}/toggle")
async def toggle_department(
    department_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    department = await session.get(Department, department_id)
    if department:
        department.is_active = not department.is_active
        session.add(department)
        await session.commit()
    return RedirectResponse(url="/admin/settings#departments", status_code=303)


@router.post("/departments/{department_id}/delete")
async def delete_department(
    department_id: uuid.UUID,
    force: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Löscht die Abteilung KASKADIEREND (siehe app.core.trash.purge_department):
    Gegenstände/Verbrauchsmaterial/Benutzer/Kategorien/Standorte/Zugriffs-
    Zuweisungen der Abteilung werden mitgelöscht, abgeschlossene Ausleih-/
    Entnahme-/Reservierungs-Historie bleibt als Text-Schnappschuss erhalten
    (nie gelöscht). Blockiert NUR bei noch OFFENEN Ausleihen/Reservierungen/
    Material-Vormerkungen - das sind aktive Geschäftsvorgänge, keine reine
    Historie. Mit force=true werden diese stattdessen automatisch
    abgeschlossen statt zu blockieren (Testdaten/Fehleingaben aufräumen,
    ohne jede Zeile erst händisch suchen zu müssen - "Trotzdem entfernen" im UI)."""
    department = await session.get(Department, department_id)
    if not department:
        return RedirectResponse(url="/admin/settings#departments", status_code=303)

    name = department.name
    error = await purge_department(session, department, force=bool(force))
    if error:
        return redirect_with_query(
            "/admin/settings", fragment="departments",
            error=f"{error} Erst zurückgeben/stornieren, oder stattdessen nur deaktivieren.",
        )

    await session.commit()
    return redirect_with_query("/admin/settings", fragment="departments", ok=f"{name} gelöscht.")


# --- Kategorien --------------------------------------------------------

@router.post("/categories/new")
async def create_category(
    name: str = Form(...),
    department_id: uuid.UUID = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(
        select(Category).where(Category.department_id == department_id, Category.name == name)
    )
    if not result.first():
        session.add(Category(name=name.strip(), department_id=department_id))
        await session.commit()
    return RedirectResponse(url="/admin/settings#categories", status_code=303)


@router.post("/categories/{category_id}/delete")
async def delete_category(
    category_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    category = await session.get(Category, category_id)
    if not category:
        return RedirectResponse(url="/admin/settings#categories", status_code=303)

    # Zusatzfelder hängen per Fremdschlüssel an der Kategorie (siehe
    # app/models/custom_field.py) - ohne diese Prüfung würde das Löschen
    # entweder an der FK-Constraint scheitern (Postgres) oder verwaiste
    # Referenzen hinterlassen. Gleiches Blocker-Muster wie delete_department oben,
    # inklusive konkreter Feldnamen statt nur einer Anzahl.
    fields_result = await session.exec(
        select(CustomFieldDefinition).where(CustomFieldDefinition.category_id == category_id).limit(4)
    )
    fields = fields_result.all()
    if fields:
        names = ", ".join(f.name for f in fields[:3])
        if len(fields) > 3:
            field_count = (
                await session.exec(
                    select(func.count()).select_from(CustomFieldDefinition).where(CustomFieldDefinition.category_id == category_id)
                )
            ).one()
            names += f", … ({field_count} gesamt)"
        message = (
            f"'{category.name}' kann nicht gelöscht werden, hat noch Zusatzfelder: {names}. "
            "Erst im Tab 'Zusatzfelder' entfernen."
        )
        return redirect_with_query("/admin/settings", fragment="categories", error=message)

    await session.delete(category)
    await session.commit()
    return RedirectResponse(url="/admin/settings#categories", status_code=303)


# --- Zusatzfelder (pro Kategorie, nur Gegenstände) ----------------------

@router.post("/custom-fields/new")
async def create_custom_field(
    category_id: uuid.UUID = Form(...),
    name: str = Form(...),
    field_type: str = Form(...),
    options: str = Form(""),
    visible_to_all: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        parsed_type = CustomFieldType(field_type)
    except ValueError:
        return redirect_with_query("/admin/settings", fragment="custom-fields", error="Ungültiger Feldtyp.")

    session.add(
        CustomFieldDefinition(
            category_id=category_id,
            name=name.strip(),
            field_type=parsed_type,
            options=options.strip() or None,
            visible_to_all=bool(visible_to_all),
        )
    )
    await session.commit()
    return redirect_with_query("/admin/settings", fragment="custom-fields", ok="Zusatzfeld angelegt.")


@router.post("/custom-fields/{field_id}/delete")
async def delete_custom_field(
    field_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    field = await session.get(CustomFieldDefinition, field_id)
    if field:
        # Zugehörige Werte an Gegenständen gehören zu diesem Feld - werden
        # mitgelöscht statt verwaist zu bleiben (kein eigenständiger Sinn
        # ohne die Definition, die Typ/Optionen vorgibt).
        values_result = await session.exec(select(CustomFieldValue).where(CustomFieldValue.field_id == field_id))
        for value in values_result.all():
            await session.delete(value)
        await session.delete(field)
        await session.commit()
    return redirect_with_query("/admin/settings", fragment="custom-fields", ok="Zusatzfeld entfernt.")


# --- Standorte ---------------------------------------------------------

@router.post("/locations/new")
async def create_location(
    name: str = Form(...),
    department_id: uuid.UUID = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(
        select(Location).where(Location.department_id == department_id, Location.name == name)
    )
    if not result.first():
        session.add(Location(name=name.strip(), department_id=department_id))
        await session.commit()
    return RedirectResponse(url="/admin/settings#locations", status_code=303)


@router.post("/locations/{location_id}/delete")
async def delete_location(
    location_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    location = await session.get(Location, location_id)
    if location:
        await session.delete(location)
        await session.commit()
    return RedirectResponse(url="/admin/settings#locations", status_code=303)


# --- Zugriff: Rolle pro Benutzer und Abteilung --------------------------

@router.post("/access/new")
async def create_access(
    user_id: uuid.UUID = Form(...),
    department_id: uuid.UUID = Form(...),
    role: str = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    if role not in ("mitarbeiter", "nutzer"):
        return RedirectResponse(url="/admin/settings#access", status_code=303)

    existing = await session.get(UserDepartmentRole, (user_id, department_id))
    if existing:
        # Schon ein Eintrag für diese Kombination -> Rolle aktualisieren statt Duplikat
        existing.role = UserRole(role)
        session.add(existing)
    else:
        session.add(UserDepartmentRole(user_id=user_id, department_id=department_id, role=UserRole(role)))
    await session.commit()
    return RedirectResponse(url="/admin/settings#access", status_code=303)


@router.post("/access/{user_id}/{department_id}/delete")
async def delete_access(
    user_id: uuid.UUID,
    department_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    entry = await session.get(UserDepartmentRole, (user_id, department_id))
    if entry:
        await session.delete(entry)
        await session.commit()
    return RedirectResponse(url="/admin/settings#access", status_code=303)


# --- E-Mail (SMTP-Konto für System-Mails) -------------------------------

@router.post("/email-settings")
async def update_email_settings(
    smtp_host: str = Form(...),
    smtp_port: int = Form(587),
    smtp_username: str = Form(""),
    smtp_password: str = Form(""),
    use_tls: str = Form(""),
    from_address: str = Form(...),
    from_name: str = Form("Scandy-Lite"),
    enabled: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await get_email_settings(session)
    if not existing:
        existing = EmailSettings(smtp_host=smtp_host, from_address=from_address)
        session.add(existing)

    existing.smtp_host = smtp_host.strip()
    existing.smtp_port = smtp_port
    existing.smtp_username = smtp_username.strip() or None
    if smtp_password:
        # Leer gelassen = vorhandenes Passwort behalten - wird nie im
        # Klartext zurück ins Formular gerendert, ein leeres Feld darf das
        # gespeicherte Passwort also nicht versehentlich löschen.
        existing.smtp_password_encrypted = encrypt_secret(smtp_password)
    existing.use_tls = bool(use_tls)
    existing.from_address = from_address.strip()
    existing.from_name = from_name.strip() or "Scandy-Lite"
    existing.enabled = bool(enabled)

    session.add(existing)
    await session.commit()
    return redirect_with_query("/admin/settings", fragment="email", ok="E-Mail-Einstellungen gespeichert.")


@router.post("/email-settings/test")
async def test_email_settings(
    test_to: str = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    html_body = templates.get_template("email/password_reset.html").render(
        username=None, reset_url="https://example.invalid/nur-ein-test"
    )
    sent = await send_email(session, test_to.strip(), "Scandy-Lite: Test-Mail", html_body)
    if sent:
        return redirect_with_query("/admin/settings", fragment="email", ok=f"Test-Mail an {test_to} verschickt.")
    return redirect_with_query(
        "/admin/settings", fragment="email",
        error="Test-Mail konnte nicht verschickt werden - Zugangsdaten/Einstellungen prüfen (Details im Server-Log).",
    )


# --- Papierkorb (soft-gelöschte Gegenstände/Material/Mitarbeiter) -------
#
# restore_trashed_*/purge_trashed_* unterscheiden sich zwischen Item/
# Consumable/User nur in Modell, Anzeigename und der zugrunde liegenden
# restore_*/purge_*-Funktion aus app.core.trash - _TrashKind bündelt das,
# die Routen selbst bleiben dünne, URL-adressierbare Wrapper.


@dataclass(frozen=True)
class _TrashKind:
    model: type
    not_found_label: str
    restore_fn: Callable
    purge_fn: Callable
    name_fn: Callable[[object], str]


_TRASH_KINDS = {
    "items": _TrashKind(Item, "Gegenstand", restore_item, purge_item, lambda e: e.name),
    "consumables": _TrashKind(Consumable, "Verbrauchsmaterial", restore_consumable, purge_consumable, lambda e: e.name),
    "users": _TrashKind(User, "Benutzer", restore_user, purge_user, lambda e: e.full_name),
}


async def _restore_trashed(session: AsyncSession, kind_key: str, entity_id: uuid.UUID):
    kind = _TRASH_KINDS[kind_key]
    entity = await session.get(kind.model, entity_id)
    if not entity or entity.deleted_at is None:
        return redirect_with_query("/admin/settings", fragment="trash", error=f"{kind.not_found_label} nicht gefunden.")
    error = await kind.restore_fn(session, entity)
    if error:
        return redirect_with_query("/admin/settings", fragment="trash", error=error)
    await session.commit()
    return redirect_with_query("/admin/settings", fragment="trash", ok=f"{kind.name_fn(entity)} wiederhergestellt.")


async def _purge_trashed(session: AsyncSession, kind_key: str, entity_id: uuid.UUID, force: str):
    kind = _TRASH_KINDS[kind_key]
    entity = await session.get(kind.model, entity_id)
    if not entity or entity.deleted_at is None:
        return redirect_with_query("/admin/settings", fragment="trash", error=f"{kind.not_found_label} nicht gefunden.")
    name = kind.name_fn(entity)
    error = await kind.purge_fn(session, entity, force=bool(force))
    if error:
        return redirect_with_query("/admin/settings", fragment="trash", error=error)
    await session.commit()
    return redirect_with_query("/admin/settings", fragment="trash", ok=f"{name} endgültig gelöscht.")


@router.post("/trash/items/{item_id}/restore")
async def restore_trashed_item(
    item_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _restore_trashed(session, "items", item_id)


@router.post("/trash/items/{item_id}/purge")
async def purge_trashed_item(
    item_id: uuid.UUID,
    force: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _purge_trashed(session, "items", item_id, force)


@router.post("/trash/consumables/{consumable_id}/restore")
async def restore_trashed_consumable(
    consumable_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _restore_trashed(session, "consumables", consumable_id)


@router.post("/trash/consumables/{consumable_id}/purge")
async def purge_trashed_consumable(
    consumable_id: uuid.UUID,
    force: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _purge_trashed(session, "consumables", consumable_id, force)


@router.post("/trash/users/{trashed_user_id}/restore")
async def restore_trashed_user(
    trashed_user_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _restore_trashed(session, "users", trashed_user_id)


@router.post("/trash/users/{trashed_user_id}/purge")
async def purge_trashed_user(
    trashed_user_id: uuid.UUID,
    force: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _purge_trashed(session, "users", trashed_user_id, force)
