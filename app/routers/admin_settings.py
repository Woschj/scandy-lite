"""
Admin-Einstellungen: Abteilungen anlegen/umbenennen/deaktivieren,
Kategorien-/Standort-Vorschläge pflegen, Benutzer verwalten, und die
Abteilungs-Rollen-Zuordnung (wer darf was in welcher Abteilung).

Bewusst schlank gehalten (ggü. dem Original-Scandy2-Systembereich): keine
Feature-Flags, kein Custom-Fields-System, kein Notification-Center - nur die
Presets, die die Formulare tatsächlich brauchen.
"""
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_department, require_admin, populate_switchable_departments
from app.core.security import hash_password
from app.core.templating import templates
from app.models.common import UserRole
from app.models.department import Department
from app.models.preset import Category, Location
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole
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
            "access_by_user": access_by_user,
            "all_access": all_access,
        },
    )


# --- Benutzer ----------------------------------------------------------

@router.post("/users/new")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    is_admin: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(select(User).where(User.username == username.strip()))
    if not result.first() and len(password) >= 8:
        new_user = User(
            username=username.strip(),
            is_admin=bool(is_admin),
            hashed_password=hash_password(password),
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
        # Abteilungs-Rollen-Zuordnungen gehen mit (sonst verwaiste Einträge)
        access_result = await session.exec(select(UserDepartmentRole).where(UserDepartmentRole.user_id == user_id))
        for entry in access_result.all():
            await session.delete(entry)
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
