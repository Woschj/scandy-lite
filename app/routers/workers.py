"""CRUD für Mitarbeiter (Worker) - die Personen, die Gegenstände ausleihen.
Kein "aktuell aktive Abteilung"-Kontext - die Abteilung ist ein Formularfeld
beim Anlegen, sonst über den Datensatz selbst bekannt."""
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_accessible_departments, get_department_roles, get_visible_department_ids, is_staff_in_department
from app.core.database import get_session
from app.core.deps import Forbidden, get_current_user, populate_nav_context, require_staff, verify_csrf
from app.core.templating import templates
from app.models.common import UserRole, utcnow
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(prefix="/workers", tags=["workers"], dependencies=[Depends(populate_nav_context), Depends(require_staff), Depends(verify_csrf)])


async def _staff_departments(session: AsyncSession, user: User):
    if user.is_admin:
        return await get_accessible_departments(session, user)
    roles = await get_department_roles(session, user)
    dept_ids = {r.department_id for r in roles if r.role == UserRole.MITARBEITER}
    if not dept_ids:
        return []
    all_accessible = await get_accessible_departments(session, user)
    return [d for d in all_accessible if d.id in dept_ids]


WORKER_SORT_COLUMNS = {"name": Worker.last_name, "barcode": Worker.barcode}


@router.get("")
async def list_workers(
    request: Request,
    q: str = "",
    status: str = "",
    sort: str = "name",
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from sqlalchemy.orm import selectinload

    stmt = (
        select(Worker)
        .where(Worker.deleted_at.is_(None))
        .order_by(WORKER_SORT_COLUMNS.get(sort, Worker.last_name))
        .options(selectinload(Worker.department))
    )
    staff_department_ids: set = set()
    if not user.is_admin:
        roles = await get_department_roles(session, user)
        staff_department_ids = {r.department_id for r in roles if r.role == UserRole.MITARBEITER}
        visible_ids = await get_visible_department_ids(session, user)
        stmt = stmt.where(Worker.department_id.in_(visible_ids))
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (Worker.first_name.ilike(like)) | (Worker.last_name.ilike(like)) | (Worker.barcode.ilike(like))
        )
    if status == "aktiv":
        stmt = stmt.where(Worker.is_active == True)  # noqa: E712
    elif status == "inaktiv":
        stmt = stmt.where(Worker.is_active == False)  # noqa: E712

    result = await session.exec(stmt)
    workers = result.all()

    return templates.TemplateResponse(
        request,
        "workers/list.html",
        {
            "user": user, "workers": workers, "q": q, "ok": ok, "error": error,
            "status": status, "sort": sort, "staff_department_ids": staff_department_ids,
        },
    )


async def _linkable_users(session: AsyncSession, exclude_worker_user_id: uuid.UUID | None = None) -> list[User]:
    """User-Logins, die noch mit keinem (anderen) Mitarbeiter-Ausweis verknüpft
    sind - fürs Verknüpfen-Dropdown beim Anlegen UND Bearbeiten."""
    linked_ids_result = await session.exec(select(Worker.user_id).where(Worker.user_id.is_not(None)))
    linked_ids = {uid for uid in linked_ids_result.all() if uid != exclude_worker_user_id}
    users_result = await session.exec(select(User).where(User.is_active == True).order_by(User.username))  # noqa: E712
    return [u for u in users_result.all() if u.id not in linked_ids]


@router.get("/new")
async def new_worker_form(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    departments = await _staff_departments(session, user)
    if not departments:
        raise Forbidden()
    linkable_users = await _linkable_users(session)
    return templates.TemplateResponse(
        request,
        "workers/form.html",
        {"user": user, "worker": None, "error": None, "departments": departments, "linkable_users": linkable_users},
    )


@router.post("/new")
async def create_worker(
    request: Request,
    barcode: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    department_id: uuid.UUID = Form(...),
    user_id: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if not await is_staff_in_department(session, user, department_id):
        raise Forbidden()

    result = await session.exec(select(Worker).where(Worker.barcode == barcode, Worker.deleted_at.is_(None)))
    if result.first():
        departments = await _staff_departments(session, user)
        linkable_users = await _linkable_users(session)
        return templates.TemplateResponse(
            request,
            "workers/form.html",
            {
                "user": user, "worker": None,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "departments": departments, "linkable_users": linkable_users,
            },
            status_code=409,
        )

    worker = Worker(barcode=barcode, first_name=first_name, last_name=last_name, department_id=department_id)
    if user_id:
        try:
            worker.user_id = uuid.UUID(user_id)
        except ValueError:
            raise Forbidden()
    session.add(worker)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return RedirectResponse(url="/workers?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/workers", status_code=303)


@router.get("/{worker_id}/edit")
async def edit_worker_form(
    request: Request,
    worker_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(Worker, worker_id)
    if not worker or worker.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, worker.department_id):
        raise Forbidden()

    # User zum Verknüpfen: noch nicht verknüpfte + der ggf. bereits verknüpfte
    linkable_users = await _linkable_users(session, exclude_worker_user_id=worker.user_id)

    return templates.TemplateResponse(
        request,
        "workers/form.html",
        {
            "user": user, "worker": worker, "error": None,
            "linkable_users": linkable_users,
        },
    )


@router.post("/{worker_id}/edit")
async def update_worker(
    request: Request,
    worker_id: uuid.UUID,
    barcode: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    is_active: str = Form(""),
    user_id: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(Worker, worker_id)
    if not worker or worker.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, worker.department_id):
        raise Forbidden()

    result = await session.exec(
        select(Worker).where(Worker.barcode == barcode, Worker.id != worker_id, Worker.deleted_at.is_(None))
    )
    if result.first():
        linkable_users = await _linkable_users(session, exclude_worker_user_id=worker.user_id)
        return templates.TemplateResponse(
            request,
            "workers/form.html",
            {
                "user": user, "worker": worker,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "linkable_users": linkable_users,
            },
            status_code=409,
        )

    worker.barcode = barcode
    worker.first_name = first_name
    worker.last_name = last_name
    worker.is_active = bool(is_active)
    if user_id:
        try:
            worker.user_id = uuid.UUID(user_id)
        except ValueError:
            raise Forbidden()
    else:
        worker.user_id = None
    session.add(worker)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return RedirectResponse(url="/workers?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/workers", status_code=303)


@router.post("/{worker_id}/delete")
async def delete_worker(
    worker_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(Worker, worker_id)
    if not worker or worker.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, worker.department_id):
        raise Forbidden()

    worker.deleted_at = utcnow()
    session.add(worker)
    await session.commit()
    return RedirectResponse(url="/workers", status_code=303)
