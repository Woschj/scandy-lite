"""
Reservierungen: eingeloggte Nutzer mit verknüpftem Mitarbeiter-Ausweis können
verfügbare Gegenstände zur Abholung vormerken. Die Ausgabe selbst passiert
weiterhin über den Scan-Workflow (dort wird die Reservierung erfüllt).
"""
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_visible_department_ids
from app.core.database import get_session
from app.core.deps import Forbidden, get_current_department, get_current_user, populate_switchable_departments
from app.core.templating import templates
from app.models.common import ItemStatus, utcnow
from app.models.department import Department
from app.models.item import Item
from app.models.reservation import Reservation
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(prefix="/reservations", tags=["reservations"], dependencies=[Depends(populate_switchable_departments)])


async def get_linked_worker(session: AsyncSession, user: User) -> Worker | None:
    result = await session.exec(
        select(Worker).where(Worker.user_id == user.id, Worker.deleted_at.is_(None), Worker.is_active == True)  # noqa: E712
    )
    return result.first()


async def get_open_reservation(session: AsyncSession, item_id: uuid.UUID) -> Reservation | None:
    result = await session.exec(
        select(Reservation)
        .where(
            Reservation.item_id == item_id,
            Reservation.fulfilled_at.is_(None),
            Reservation.cancelled_at.is_(None),
        )
        .options(selectinload(Reservation.worker))
    )
    return result.first()


@router.get("")
async def my_reservations(
    request: Request,
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    worker = await get_linked_worker(session, user)

    reservations = []
    if worker:
        result = await session.exec(
            select(Reservation)
            .where(
                Reservation.worker_id == worker.id,
                Reservation.fulfilled_at.is_(None),
                Reservation.cancelled_at.is_(None),
            )
            .options(selectinload(Reservation.item))
            .order_by(Reservation.created_at.desc())
        )
        reservations = result.all()

    # Admins sehen zusätzlich alle offenen Reservierungen der gewählten Abteilung
    all_open = []
    if user.is_admin:
        stmt = (
            select(Reservation)
            .where(Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
            .options(selectinload(Reservation.item), selectinload(Reservation.worker))
            .order_by(Reservation.created_at.desc())
        )
        if department:
            stmt = stmt.where(Reservation.department_id == department.id)
        all_open = (await session.exec(stmt)).all()

    return templates.TemplateResponse(
        request,
        "reservations/list.html",
        {
            "user": user, "department": department, "worker": worker,
            "reservations": reservations, "all_open": all_open,
            "ok": ok, "error": error,
        },
    )


@router.post("/items/{item_id}")
async def reserve_item(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await get_linked_worker(session, user)
    if not worker:
        return RedirectResponse(
            url="/reservations?error=Dein+Login+ist+mit+keinem+Mitarbeiter-Ausweis+verknüpft.+Bitte+an+Admin+wenden.",
            status_code=303,
        )

    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise Forbidden()

    # Berechtigung: Admin darf immer. Sonst muss die Abteilung des Gegenstands
    # zu den für DIESEN User sichtbaren Abteilungen gehören (siehe
    # app/core/access.py - jede Rolle, Mitarbeiter wie Nutzer, gewährt
    # Sichtbarkeit/Reservierbarkeit in ihren jeweiligen Abteilungen).
    visible_ids = await get_visible_department_ids(session, user)
    if visible_ids is not None and item.department_id not in visible_ids:
        raise Forbidden()

    if item.status != ItemStatus.VERFUEGBAR:
        return RedirectResponse(url="/reservations?error=Gegenstand+ist+aktuell+nicht+verfügbar.", status_code=303)

    if await get_open_reservation(session, item.id):
        return RedirectResponse(url="/reservations?error=Gegenstand+ist+bereits+reserviert.", status_code=303)

    reservation = Reservation(item_id=item.id, worker_id=worker.id, department_id=item.department_id)
    session.add(reservation)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return RedirectResponse(url="/reservations?error=Gegenstand+wurde+soeben+bereits+reserviert.", status_code=303)

    return RedirectResponse(url=f"/reservations?ok={item.name}+reserviert.", status_code=303)


@router.post("/{reservation_id}/cancel")
async def cancel_reservation(
    reservation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    reservation = await session.get(Reservation, reservation_id)
    if not reservation or not reservation.is_open:
        raise Forbidden()

    # Stornieren darf: der Reservierende selbst oder ein Admin
    worker = await get_linked_worker(session, user)
    is_owner = worker and reservation.worker_id == worker.id
    if not is_owner and not user.is_admin:
        raise Forbidden()

    reservation.cancelled_at = utcnow()
    session.add(reservation)
    await session.commit()
    return RedirectResponse(url="/reservations?ok=Reservierung+storniert.", status_code=303)
