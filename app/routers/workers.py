"""CRUD für Mitarbeiter (Worker) - die Personen, die Gegenstände ausleihen."""
import uuid


from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import Forbidden, get_current_department, get_current_user
from app.core.templating import templates
from app.models.common import utcnow
from app.models.department import Department
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(prefix="/workers", tags=["workers"])


@router.get("")
async def list_workers(
    request: Request,
    q: str = "",
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
        {"user": user, "department": department, "workers": workers, "q": q},
    )


@router.get("/new")
async def new_worker_form(
    request: Request,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
):
    if not department:
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
    await session.commit()
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
    if not worker or worker.deleted_at is not None or (department and worker.department_id != department.id):
        raise Forbidden()

    return templates.TemplateResponse(
        request,
        "workers/form.html",
        {"user": user, "department": department, "worker": worker, "error": None},
    )


@router.post("/{worker_id}/edit")
async def update_worker(
    request: Request,
    worker_id: uuid.UUID,
    barcode: str = Form(...),
    first_name: str = Form(...),
    last_name: str = Form(...),
    is_active: str = Form(""),
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(Worker, worker_id)
    if not worker or worker.deleted_at is not None or (department and worker.department_id != department.id):
        raise Forbidden()

    result = await session.exec(
        select(Worker).where(Worker.barcode == barcode, Worker.id != worker_id, Worker.deleted_at.is_(None))
    )
    if result.first():
        return templates.TemplateResponse(
            request,
            "workers/form.html",
            {
                "user": user, "department": department, "worker": worker,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
            },
            status_code=409,
        )

    worker.barcode = barcode
    worker.first_name = first_name
    worker.last_name = last_name
    worker.is_active = bool(is_active)
    session.add(worker)
    await session.commit()
    return RedirectResponse(url="/workers", status_code=303)


@router.post("/{worker_id}/delete")
async def delete_worker(
    worker_id: uuid.UUID,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(Worker, worker_id)
    if not worker or worker.deleted_at is not None or (department and worker.department_id != department.id):
        raise Forbidden()

    worker.deleted_at = utcnow()
    session.add(worker)
    await session.commit()
    return RedirectResponse(url="/workers", status_code=303)
