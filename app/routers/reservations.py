"""
Reservierungen: eingeloggte Nutzer mit verknüpftem Mitarbeiter-Ausweis können
verfügbare Gegenstände zur Abholung vormerken. Die Ausgabe selbst passiert
weiterhin über den Scan-Workflow (dort wird die Reservierung erfüllt).
"""
import uuid

from fastapi import APIRouter, Depends, Form, Request
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


async def _try_reserve(
    session: AsyncSession, user: User, worker: Worker, item_id: uuid.UUID
) -> tuple[bool, str]:
    """Versucht, EINEN Gegenstand zu reservieren. Gibt (erfolgreich, Meldung)
    zurück, statt zu werfen/umzuleiten - so lässt sich dieselbe Logik sowohl
    für die Einzel-Reservierung als auch für den gesammelten Warenkorb-Versand
    verwenden (dort darf ein einzelner Fehlschlag nicht den ganzen Vorgang
    abbrechen, sondern muss pro Gegenstand gemeldet werden)."""
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None:
        return False, "Gegenstand nicht gefunden."

    visible_ids = await get_visible_department_ids(session, user)
    if visible_ids is not None and item.department_id not in visible_ids:
        return False, f"{item.name}: keine Berechtigung für diese Abteilung."

    if item.status != ItemStatus.VERFUEGBAR:
        return False, f"{item.name}: aktuell nicht verfügbar."

    if await get_open_reservation(session, item.id):
        return False, f"{item.name}: bereits reserviert."

    reservation = Reservation(item_id=item.id, worker_id=worker.id, department_id=item.department_id)
    session.add(reservation)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return False, f"{item.name}: wurde soeben bereits reserviert."

    return True, item.name


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

    ok, message = await _try_reserve(session, user, worker, item_id)
    if not ok:
        if message == "Gegenstand nicht gefunden.":
            raise Forbidden()
        return RedirectResponse(url=f"/reservations?error={message}", status_code=303)
    return RedirectResponse(url=f"/reservations?ok={message}+reserviert.", status_code=303)


@router.get("/cart")
async def cart_page(
    request: Request,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
):
    """Reine Seiten-Hülle - der Inhalt (welche Gegenstände im Warenkorb sind)
    kommt clientseitig aus localStorage (app/static/js/cart.js), Details dazu
    werden per fetch() von /reservations/cart/items nachgeladen. So bleibt der
    Warenkorb über mehrere Seitenaufrufe/Abteilungswechsel hinweg erhalten,
    ohne dass wir dafür einen eigenen Datenbank-Tabellen-Umweg bräuchten."""
    return templates.TemplateResponse(
        request, "reservations/cart.html",
        {"user": user, "department": department},
    )


@router.get("/cart/items")
async def cart_items(
    ids: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """JSON-Endpunkt für die Warenkorb-Seite: liefert zu einer Liste von
    Item-IDs (aus localStorage) die aktuellen Anzeige-Infos, inkl. eines
    Verfügbarkeits-Hinweises - der Warenkorb selbst ist rein clientseitig,
    der Stand eines Gegenstands kann sich also zwischenzeitlich geändert
    haben (von jemand anderem reserviert, gelöscht, ...)."""
    id_list = [i.strip() for i in ids.split(",") if i.strip()]
    if not id_list:
        return {"items": []}

    try:
        parsed_ids = [uuid.UUID(i) for i in id_list]
    except ValueError:
        return {"items": []}

    visible_ids = await get_visible_department_ids(session, user)

    result = await session.exec(
        select(Item).where(Item.id.in_(parsed_ids), Item.deleted_at.is_(None)).options(selectinload(Item.department))
    )
    items = {str(i.id): i for i in result.all()}

    response_items = []
    for item_id in id_list:
        item = items.get(item_id)
        if not item or (visible_ids is not None and item.department_id not in visible_ids):
            response_items.append({"id": item_id, "found": False})
            continue
        open_res = await get_open_reservation(session, item.id)
        response_items.append({
            "id": str(item.id),
            "found": True,
            "name": item.name,
            "barcode": item.barcode,
            "department": item.department.name if item.department else "",
            "available": item.status.value == "verfuegbar" and open_res is None,
            "status_label": "Verfügbar" if item.status.value == "verfuegbar" and open_res is None else (
                "Bereits reserviert" if open_res else item.status.value
            ),
        })
    return {"items": response_items}


@router.post("/cart/submit")
async def cart_submit(
    item_ids: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await get_linked_worker(session, user)
    if not worker:
        return RedirectResponse(
            url="/reservations?error=Dein+Login+ist+mit+keinem+Mitarbeiter-Ausweis+verknüpft.+Bitte+an+Admin+wenden.",
            status_code=303,
        )

    succeeded, failed = [], []
    for raw_id in item_ids:
        try:
            item_id = uuid.UUID(raw_id)
        except ValueError:
            continue
        ok, message = await _try_reserve(session, user, worker, item_id)
        (succeeded if ok else failed).append(message)

    if not succeeded and not failed:
        return RedirectResponse(url="/reservations/cart?error=Warenkorb+war+leer.", status_code=303)

    parts = []
    if succeeded:
        parts.append(f"ok={len(succeeded)}+Gegenstand(e)+reserviert.")
    if failed:
        parts.append("error=" + "+/+".join(failed))
    return RedirectResponse(url="/reservations?" + "&".join(parts), status_code=303)


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
