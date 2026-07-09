"""
Admin-Einstellungen: Abteilungen anlegen/umbenennen/deaktivieren,
Kategorien- und Standort-Vorschläge pro Abteilung pflegen.

Bewusst schlank gehalten (ggü. dem Original-Scandy2-Systembereich): keine
Feature-Flags, kein Custom-Fields-System, kein Notification-Center - nur die
Presets, die die Formulare in Phase 3 tatsächlich brauchen.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_department, require_admin, populate_switchable_departments
from app.core.security import hash_password
from app.core.templating import templates
from app.models.common import UserRole
from app.models.department import Department
from app.models.group import GroupDepartmentAccess, WorkerGroup
from app.models.preset import Category, Location
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(populate_switchable_departments)])


@router.get("/settings")
async def settings_page(
    request: Request,
    user: User = Depends(require_admin),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    departments = (await session.exec(select(Department).order_by(Department.name))).all()
    categories = (await session.exec(
        select(Category).order_by(Category.department_id, Category.name)
    )).all()
    locations = (await session.exec(
        select(Location).order_by(Location.department_id, Location.name)
    )).all()
    users = (await session.exec(select(User).order_by(User.username))).all()

    groups = (await session.exec(select(WorkerGroup).order_by(WorkerGroup.name))).all()
    group_access = (await session.exec(select(GroupDepartmentAccess))).all()
    # department_ids je Gruppe für die Anzeige/Checkboxen aufbereiten
    group_dept_ids: dict = {}
    for link in group_access:
        group_dept_ids.setdefault(link.group_id, set()).add(link.department_id)

    return templates.TemplateResponse(
        request,
        "admin/settings.html",
        {
            "user": user,
            "department": department,
            "departments": departments,
            "categories": categories,
            "locations": locations,
            "users": users,
            "groups": groups,
            "group_dept_ids": group_dept_ids,
        },
    )


# --- Benutzer ----------------------------------------------------------

@router.post("/users/new")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form("mitarbeiter"),
    department_id: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(select(User).where(User.username == username.strip()))
    if not result.first() and len(password) >= 8:
        new_user = User(
            username=username.strip(),
            role=UserRole(role) if role in ("admin", "mitarbeiter", "nutzer") else UserRole.NUTZER,
            hashed_password=hash_password(password),
            department_id=uuid.UUID(department_id) if department_id else None,
        )
        session.add(new_user)
        await session.commit()
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


@router.post("/users/{user_id}/delete")
async def delete_user(
    user_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Echtes Löschen (nicht nur Deaktivieren) - bei Usern unproblematisch,
    weil keine Ausleih-/Historien-Daten direkt am User hängen (die referenzieren
    Worker, nicht User). Anders als bei Gegenständen/Mitarbeitern, wo Soft-Delete
    bewusst bleibt, um die Historie nicht zu zerreißen."""
    if user_id == user.id:
        return RedirectResponse(url="/admin/settings?error=Eigenes+Konto+kann+nicht+gelöscht+werden.#users", status_code=303)

    target = await session.get(User, user_id)
    if target:
        # Verknüpften Worker-Datensatz nicht mitlöschen, nur die Verknüpfung lösen
        linked_result = await session.exec(select(Worker).where(Worker.user_id == user_id))
        for worker in linked_result.all():
            worker.user_id = None
            session.add(worker)
        await session.delete(target)
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
    if category:
        await session.delete(category)
        await session.commit()
    return RedirectResponse(url="/admin/settings#categories", status_code=303)


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


# --- Nutzergruppen (Ausleihberechtigung, entkoppelt von der Heimat-Abteilung) ----

@router.post("/groups/new")
async def create_group(
    name: str = Form(...),
    department_ids: list[str] = Form(default=[]),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    name = name.strip()
    result = await session.exec(select(WorkerGroup).where(WorkerGroup.name == name))
    if not name or result.first():
        return RedirectResponse(url="/admin/settings#groups", status_code=303)

    group = WorkerGroup(name=name)
    session.add(group)
    await session.commit()
    await session.refresh(group)

    for dept_id in department_ids:
        try:
            session.add(GroupDepartmentAccess(group_id=group.id, department_id=uuid.UUID(dept_id)))
        except ValueError:
            continue
    await session.commit()
    return RedirectResponse(url="/admin/settings#groups", status_code=303)


@router.post("/groups/{group_id}/access")
async def update_group_access(
    group_id: uuid.UUID,
    department_ids: list[str] = Form(default=[]),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Setzt die Abteilungs-Zugriffe einer Gruppe komplett neu (einfacher als
    Diffs zu berechnen - bei überschaubarer Abteilungs-/Gruppenzahl unproblematisch)."""
    group = await session.get(WorkerGroup, group_id)
    if not group:
        return RedirectResponse(url="/admin/settings#groups", status_code=303)

    existing = (await session.exec(
        select(GroupDepartmentAccess).where(GroupDepartmentAccess.group_id == group_id)
    )).all()
    for link in existing:
        await session.delete(link)

    for dept_id in department_ids:
        try:
            session.add(GroupDepartmentAccess(group_id=group_id, department_id=uuid.UUID(dept_id)))
        except ValueError:
            continue
    await session.commit()
    return RedirectResponse(url="/admin/settings#groups", status_code=303)


@router.post("/groups/{group_id}/delete")
async def delete_group(
    group_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    group = await session.get(WorkerGroup, group_id)
    if group:
        # Verknüpfte Worker verlieren die Gruppe (fallen auf ihre department_id
        # zurück statt kaputte Referenzen zu behalten), Zugriffs-Verknüpfungen
        # werden mitgelöscht.
        workers_result = await session.exec(select(Worker).where(Worker.group_id == group_id))
        for w in workers_result.all():
            w.group_id = None
            session.add(w)
        access_result = await session.exec(select(GroupDepartmentAccess).where(GroupDepartmentAccess.group_id == group_id))
        for link in access_result.all():
            await session.delete(link)
        await session.delete(group)
        await session.commit()
    return RedirectResponse(url="/admin/settings#groups", status_code=303)
