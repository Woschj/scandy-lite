"""
Admin-Einstellungsseite: aggregiert Abteilungen, Kategorien/Standorte,
Benutzer, Zusatzfelder, E-Mail-Einstellungen, Papierkorb und Update-Status
für die Tab-Ansicht (admin/settings.html).

Die eigentlichen Aktionen (anlegen/bearbeiten/löschen) sitzen in eigenen,
fachlich geschnittenen Routern - dieses Modul liefert nur die zusammen-
gesetzte Übersichtsseite:
- admin_pending_accounts.py - ausstehende SSO-Freischaltungen
- admin_users.py - Benutzerverwaltung
- admin_departments.py - Abteilungsverwaltung
- admin_presets.py - Kategorien/Standorte/Zusatzfelder
- admin_email.py - SMTP-Einstellungen
- admin_trash.py - Papierkorb
- admin_update.py - In-App-Update (native Proxmox-LXC)
- admin_import.py - Scandy2-Migration

Bewusst schlank gehalten (ggü. dem Original-Scandy2-Systembereich): kein
Feature-Flags-System, kein Notification-Center - nur die Presets, die die
Formulare tatsächlich brauchen.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.changelog import parse_changelog
from app.core.config import get_settings
from app.core.database import get_session
from app.core.deps import populate_nav_context, require_admin, verify_csrf
from app.core.email import get_email_settings
from app.core.self_update import get_cached_check
from app.core.templating import templates
from app.core.trash import get_trash_entries
from app.models.custom_field import CustomFieldDefinition
from app.models.department import Department
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
    users = (await session.exec(
        select(User).where(User.deleted_at.is_(None)).options(selectinload(User.department)).order_by(User.username)
    )).all()

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

    native_lxc_deployment = get_settings().NATIVE_LXC_DEPLOYMENT
    update_check = get_cached_check() if native_lxc_deployment else None

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
            "email_settings": email_settings,
            "custom_fields": custom_fields,
            "trash_items": trash_items,
            "trash_consumables": trash_consumables,
            "trash_users": trash_users,
            "version": __version__,
            "changelog_releases": parse_changelog(),
            "native_lxc_deployment": native_lxc_deployment,
            "update_check": update_check,
            "ok": ok,
            "error": error,
        },
    )
