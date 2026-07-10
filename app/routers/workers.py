"""CRUD für Mitarbeiter (Worker) - die Personen, die Gegenstände ausleihen."""
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import is_staff_in_department
from app.core.database import get_session
from app.core.deps import Forbidden, get_current_department, get_current_user, populate_switchable_departments, require_staff
from app.core.templating import templates
from app.models.common import utcnow
from app.models.department import Department
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(prefix="/workers", tags=["workers"], dependencies=[Depends(populate_switchable_departments), Depends(require_staff)])


@router.get("")
async def list_workers(
    request: Request,
    q: str = "",
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Worker).where(Worker.deleted_at.is_(None)).order_by(Worker.last_name)
    if department:
        stmt = stmt.where(Worker.department_id == department.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where(
            (Worker.first_name.ilike(like)) | (Worker.last_name.ilike(like)) | (Worker.barcode.ilike(like))
        )

    result = await session.exec(stmt)
    workers = result.all()

    return templates.TemplateResponse(
        request,
        "workers/list.html",
        {"user": user, "department": department, "workers": workers, "q": q, "ok": ok, "error": error},
    )


@router.get("/new")
async def new_worker_form(
    request: Request,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    if not department:
        raise Forbidden()
    if not await is_staff_in_department(session, user, department.id):
        raise Forbidden()
    return templates.TemplateResponse(
        request,
        "workers/form.html",
        {"user": user, "department": department, "worker": None, "error": None},
    )


@router.post("/new")
async def create_worker(
    request: Request,
    barcode: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    if not department:
        raise Forbidden()
    if not await is_staff_in_department(session, user, department.id):
        raise Forbidden()

    result = await session.exec(select(Worker).where(Worker.barcode == barcode, Worker.deleted_at.is_(None)))
    if result.first():
        return templates.TemplateResponse(
            request,
            "workers/form.html",
            {
                "user": user, "department": department, "worker": None,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
            },
            status_code=409,
        )

    worker = Worker(barcode=barcode, first_name=first_name, last_name=last_name, department_id=department.id)
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
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(Worker, worker_id)
    if not worker or worker.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, worker.department_id):
        raise Forbidden()

    # User zum Verknüpfen: noch nicht verknüpfte + der ggf. bereits verknüpfte
    linked_ids_result = await session.exec(select(Worker.user_id).where(Worker.user_id.is_not(None)))
    linked_ids = {uid for uid in linked_ids_result.all() if uid != worker.user_id}
    users_result = await session.exec(select(User).where(User.is_active == True).order_by(User.username))  # noqa: E712
    linkable_users = [u for u in users_result.all() if u.id not in linked_ids]

    return templates.TemplateResponse(
        request,
        "workers/form.html",
        {
            "user": user, "department": department, "worker": worker, "error": None,
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
    department: Department | None = Depends(get_current_department),
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
        linked_ids_result = await session.exec(select(Worker.user_id).where(Worker.user_id.is_not(None)))
        linked_ids = {uid for uid in linked_ids_result.all() if uid != worker.user_id}
        users_result = await session.exec(select(User).where(User.is_active == True).order_by(User.username))  # noqa: E712
        linkable_users = [u for u in users_result.all() if u.id not in linked_ids]
        return templates.TemplateResponse(
            request,
            "workers/form.html",
            {
                "user": user, "department": department, "worker": worker,
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
