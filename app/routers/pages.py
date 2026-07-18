"""
Startseite nach dem Login: Kennzahlen + Kanban-Board der laufenden Vorgänge
(offene Reservierungen -> aktive Ausleihen). Zeigt immer alles, wozu der
jeweilige User Zugriff hat (kein "aktuell aktive Abteilung"-Kontext).
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import selectinload
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_visible_department_ids
from app.core.database import get_session
from app.core.deps import get_current_user, populate_nav_context
from app.core.templating import templates
from app.models.consumable import Consumable
from app.models.item import Item
from app.models.lending import Lending
from app.models.reservation import Reservation
from app.models.user import User

router = APIRouter(tags=["pages"], dependencies=[Depends(populate_nav_context)])


@router.get("/")
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    visible_ids = await get_visible_department_ids(session, user)  # None = Admin (alles)

    # Nur für Admins relevant (nur sie können freischalten) - für alle
    # anderen keine zusätzliche Abfrage.
    pending_accounts_count = 0
    if user.is_admin:
        pending_stmt = select(func.count()).select_from(User).where(User.approved_at.is_(None), User.deleted_at.is_(None))
        pending_accounts_count = (await session.exec(pending_stmt)).one()

    item_stmt = select(func.count()).select_from(Item).where(Item.deleted_at.is_(None))
    consumable_stmt = select(func.count()).select_from(Consumable).where(Consumable.deleted_at.is_(None))
    # Nur User mit Barcode zaehlen als "Mitarbeiter" (Ausweis-Traeger) - ein
    # reiner Login ohne Ausweis (z.B. ein Admin-Systemzugang) ist kein
    # Mitarbeiter im Sinne dieser Kachel.
    worker_stmt = select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.barcode.is_not(None))
    if visible_ids is not None:
        item_stmt = item_stmt.where(Item.department_id.in_(visible_ids))
        consumable_stmt = consumable_stmt.where(Consumable.department_id.in_(visible_ids))
        worker_stmt = worker_stmt.where(User.department_id.in_(visible_ids))

    item_count = (await session.exec(item_stmt)).one()
    consumable_count = (await session.exec(consumable_stmt)).one()
    worker_count = (await session.exec(worker_stmt)).one()

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
    if visible_ids is not None:
        res_stmt = res_stmt.where(Reservation.department_id.in_(visible_ids))
        lend_stmt = lend_stmt.where(Lending.department_id.in_(visible_ids))

    open_reservations = (await session.exec(res_stmt)).all()
    active_lendings = (await session.exec(lend_stmt)).all()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "pending_accounts_count": pending_accounts_count,
            "item_count": item_count,
            "consumable_count": consumable_count,
            "worker_count": worker_count,
            "open_reservations": open_reservations,
            "active_lendings": active_lendings,
        },
    )
