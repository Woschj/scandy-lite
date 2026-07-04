"""
Startseite nach dem Login: Kennzahlen + Kanban-Board der laufenden Vorgänge
(offene Reservierungen -> aktive Ausleihen).
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import selectinload
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_department, get_current_user, populate_switchable_departments
from app.core.templating import templates
from app.models.consumable import Consumable
from app.models.department import Department
from app.models.item import Item
from app.models.lending import Lending
from app.models.reservation import Reservation
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(tags=["pages"], dependencies=[Depends(populate_switchable_departments)])


@router.get("/")
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    item_count = 0
    consumable_count = 0
    worker_count = 0
    if department:
        result = await session.exec(
            select(func.count()).select_from(Item).where(
                Item.department_id == department.id, Item.deleted_at.is_(None)
            )
        )
        item_count = result.one()

        result = await session.exec(
            select(func.count()).select_from(Consumable).where(
                Consumable.department_id == department.id, Consumable.deleted_at.is_(None)
            )
        )
        consumable_count = result.one()

        result = await session.exec(
            select(func.count()).select_from(Worker).where(
                Worker.department_id == department.id, Worker.deleted_at.is_(None)
            )
        )
        worker_count = result.one()

    # Kanban-Spalten: offene Reservierungen und aktive Ausleihen
    res_stmt = (
        select(Reservation)
        .where(Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
        .options(selectinload(Reservation.item), selectinload(Reservation.worker))
        .order_by(Reservation.created_at.desc())
        .limit(50)
    )
    lend_stmt = (
        select(Lending)
        .where(Lending.returned_at.is_(None))
        .options(selectinload(Lending.item), selectinload(Lending.worker))
        .order_by(Lending.lent_at.desc())
        .limit(50)
    )
    if department:
        res_stmt = res_stmt.where(Reservation.department_id == department.id)
        lend_stmt = lend_stmt.where(Lending.department_id == department.id)

    open_reservations = (await session.exec(res_stmt)).all()
    active_lendings = (await session.exec(lend_stmt)).all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "department": department,
            "item_count": item_count,
            "consumable_count": consumable_count,
            "worker_count": worker_count,
            "open_reservations": open_reservations,
            "active_lendings": active_lendings,
        },
    )
