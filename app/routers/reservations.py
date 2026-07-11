"""
Reservierungen: eingeloggte Nutzer mit verknüpftem Mitarbeiter-Ausweis können
verfügbare Gegenstände UND Mengen Verbrauchsmaterial zur Abholung vormerken.
Die Ausgabe/Entnahme selbst passiert weiterhin über den Scan-Workflow.

Der Warenkorb selbst (welche Einträge vorgemerkt sind, bevor abgeschickt
wird) ist rein clientseitig (localStorage, app/static/js/cart.js) - hier im
Backend gibt es dafür keine eigene Tabelle, nur die JSON-Detailabfrage und
den gesammelten Versand.
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
from app.core.deps import Forbidden, get_current_user, populate_nav_context, verify_csrf
from app.core.responses import redirect_with_query
from app.core.templating import templates
from app.models.common import ItemStatus, utcnow
from app.models.consumable import Consumable
from app.models.consumable_reservation import ConsumableReservation
from app.models.item import Item
from app.models.reservation import Reservation
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(prefix="/reservations", tags=["reservations"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


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


async def get_open_consumable_reservations(session: AsyncSession, consumable_id: uuid.UUID) -> list[ConsumableReservation]:
    result = await session.exec(
        select(ConsumableReservation).where(
            ConsumableReservation.consumable_id == consumable_id,
            ConsumableReservation.fulfilled_at.is_(None),
            ConsumableReservation.cancelled_at.is_(None),
        )
    )
    return list(result.all())


@router.get("")
async def my_reservations(
    request: Request,
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await get_linked_worker(session, user)

    reservations = []
    consumable_reservations = []
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

        result = await session.exec(
            select(ConsumableReservation)
            .where(
                ConsumableReservation.worker_id == worker.id,
                ConsumableReservation.fulfilled_at.is_(None),
                ConsumableReservation.cancelled_at.is_(None),
            )
            .options(selectinload(ConsumableReservation.consumable))
            .order_by(ConsumableReservation.created_at.desc())
        )
        consumable_reservations = result.all()

    # Admins sehen zusätzlich alle offenen Reservierungen - nach Person
    # GRUPPIERT (nicht jede einzeln), damit z.B. "20 Gegenstände von einer
    # Person" nicht als 20 einzelne Zeilen erscheint. Aufklappbar in der
    # Vorlage (natives <details>, kein JS nötig).
    open_groups = []
    if user.is_admin:
        stmt = (
            select(Reservation)
            .where(Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
            .options(selectinload(Reservation.item), selectinload(Reservation.worker))
            .order_by(Reservation.created_at.desc())
        )
        all_open = (await session.exec(stmt)).all()

        cstmt = (
            select(ConsumableReservation)
            .where(ConsumableReservation.fulfilled_at.is_(None), ConsumableReservation.cancelled_at.is_(None))
            .options(selectinload(ConsumableReservation.consumable), selectinload(ConsumableReservation.worker))
            .order_by(ConsumableReservation.created_at.desc())
        )
        all_open_consumables = (await session.exec(cstmt)).all()

        groups_by_worker: dict = {}
        for r in all_open:
            if not r.worker:
                continue
            g = groups_by_worker.setdefault(r.worker.id, {"worker": r.worker, "item_reservations": [], "consumables": []})
            g["item_reservations"].append(r)
        for r in all_open_consumables:
            if not r.worker:
                continue
            g = groups_by_worker.setdefault(r.worker.id, {"worker": r.worker, "item_reservations": [], "consumables": []})
            g["consumables"].append(r)

        open_groups = sorted(groups_by_worker.values(), key=lambda g: g["worker"].last_name)

    return templates.TemplateResponse(
        request,
        "reservations/list.html",
        {
            "user": user, "worker": worker,
            "reservations": reservations, "consumable_reservations": consumable_reservations,
            "open_groups": open_groups,
            "ok": ok, "error": error,
        },
    )


async def _try_reserve_item(
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


async def _try_reserve_consumable(
    session: AsyncSession, user: User, worker: Worker, consumable_id: uuid.UUID, quantity: int
) -> tuple[bool, str]:
    """Wie _try_reserve_item, aber für Verbrauchsmaterial. Bewusst KEIN harter
    Bestands-Held: mehrere Personen können denselben Bestand gleichzeitig
    anfragen (Personal entscheidet beim Scannen). Es wird lediglich davor
    gewarnt, wenn die Summe aus bereits offenen Vormerkungen + dieser neuen
    Anfrage den aktuellen Bestand übersteigt - blockiert aber nicht hart,
    da der Bestand bis zur Abholung noch aufgefüllt werden könnte."""
    consumable = await session.get(Consumable, consumable_id)
    if not consumable or consumable.deleted_at is not None:
        return False, "Verbrauchsmaterial nicht gefunden."

    if quantity <= 0:
        return False, f"{consumable.name}: ungültige Menge."

    visible_ids = await get_visible_department_ids(session, user)
    if visible_ids is not None and consumable.department_id not in visible_ids:
        return False, f"{consumable.name}: keine Berechtigung für diese Abteilung."

    if consumable.quantity <= 0:
        return False, f"{consumable.name}: aktuell nicht auf Lager."

    open_reservations = await get_open_consumable_reservations(session, consumable.id)
    already_reserved = sum(r.quantity for r in open_reservations)
    if already_reserved + quantity > consumable.quantity:
        return False, f"{consumable.name}: nicht genug Bestand übrig (bereits {already_reserved} vorgemerkt)."

    reservation = ConsumableReservation(
        consumable_id=consumable.id, worker_id=worker.id, department_id=consumable.department_id, quantity=quantity,
    )
    session.add(reservation)
    await session.commit()
    return True, f"{quantity}x {consumable.name}"


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

    ok, message = await _try_reserve_item(session, user, worker, item_id)
    if not ok:
        if message == "Gegenstand nicht gefunden.":
            raise Forbidden()
        return redirect_with_query("/reservations", error=message)
    return redirect_with_query("/reservations", ok=f"{message} reserviert.")


@router.get("/cart")
async def cart_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Reine Seiten-Hülle - der Inhalt (welche Einträge im Warenkorb sind)
    kommt clientseitig aus localStorage (app/static/js/cart.js), Details dazu
    werden per fetch() von /reservations/cart/items nachgeladen."""
    return templates.TemplateResponse(
        request, "reservations/cart.html",
        {"user": user},
    )


@router.get("/cart/items")
async def cart_items(
    item_ids: str = "",
    consumable_ids: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """JSON-Endpunkt für die Warenkorb-Seite: liefert zu den im Warenkorb
    (localStorage) vorgemerkten IDs die aktuellen Anzeige-Infos, inkl. eines
    Verfügbarkeits-Hinweises - der Warenkorb selbst ist rein clientseitig,
    der Stand eines Eintrags kann sich also zwischenzeitlich geändert haben
    (von jemand anderem reserviert, Bestand verändert, gelöscht, ...).

    consumable_ids kommt im Format "id:menge,id:menge" (Menge = die im
    Warenkorb gewählte, nicht die aktuell verfügbare)."""
    visible_ids = await get_visible_department_ids(session, user)

    response = {"items": [], "consumables": []}

    id_list = [i.strip() for i in item_ids.split(",") if i.strip()]
    if id_list:
        try:
            parsed_ids = [uuid.UUID(i) for i in id_list]
        except ValueError:
            parsed_ids = []
        result = await session.exec(
            select(Item).where(Item.id.in_(parsed_ids), Item.deleted_at.is_(None)).options(selectinload(Item.department))
        )
        items_by_id = {str(i.id): i for i in result.all()}
        for item_id in id_list:
            item = items_by_id.get(item_id)
            if not item or (visible_ids is not None and item.department_id not in visible_ids):
                response["items"].append({"id": item_id, "found": False})
                continue
            open_res = await get_open_reservation(session, item.id)
            available = item.status.value == "verfuegbar" and open_res is None
            response["items"].append({
                "id": str(item.id), "found": True, "name": item.name, "barcode": item.barcode,
                "department": item.department.name if item.department else "",
                "available": available,
                "status_label": "Verfügbar" if available else ("Bereits reserviert" if open_res else item.status.value),
            })

    consumable_entries = []
    for part in consumable_ids.split(","):
        part = part.strip()
        if not part or ":" not in part:
            continue
        cid, _, qty_str = part.partition(":")
        try:
            consumable_entries.append((uuid.UUID(cid), max(1, int(qty_str))))
        except ValueError:
            continue

    if consumable_entries:
        result = await session.exec(
            select(Consumable)
            .where(Consumable.id.in_([cid for cid, _ in consumable_entries]), Consumable.deleted_at.is_(None))
            .options(selectinload(Consumable.department))
        )
        consumables_by_id = {str(c.id): c for c in result.all()}
        for cid, requested_qty in consumable_entries:
            consumable = consumables_by_id.get(str(cid))
            if not consumable or (visible_ids is not None and consumable.department_id not in visible_ids):
                response["consumables"].append({"id": str(cid), "found": False})
                continue
            open_reservations = await get_open_consumable_reservations(session, consumable.id)
            already_reserved = sum(r.quantity for r in open_reservations)
            available = (already_reserved + requested_qty) <= consumable.quantity
            response["consumables"].append({
                "id": str(consumable.id), "found": True, "name": consumable.name, "barcode": consumable.barcode,
                "department": consumable.department.name if consumable.department else "",
                "unit": consumable.unit, "requested_quantity": requested_qty,
                "available": available,
                "status_label": "Verfügbar" if available else "Nicht genug Bestand mehr verfügbar",
            })

    return response


@router.post("/cart/submit")
async def cart_submit(
    item_ids: list[str] = Form(default=[]),
    consumable_ids: list[str] = Form(default=[]),
    consumable_quantities: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await get_linked_worker(session, user)
    if not worker:
        return redirect_with_query(
            "/reservations",
            error="Dein Login ist mit keinem Mitarbeiter-Ausweis verknüpft. Bitte an Admin wenden.",
        )

    succeeded, failed = [], []

    for raw_id in item_ids:
        try:
            item_id = uuid.UUID(raw_id)
        except ValueError:
            continue
        ok, message = await _try_reserve_item(session, user, worker, item_id)
        (succeeded if ok else failed).append(message)

    # consumable_ids und consumable_quantities kommen als parallele Listen
    # (gleicher Index = zusammengehöriges Paar) - das Warenkorb-Formular
    # erzeugt für jeden Verbrauchsmaterial-Eintrag zwei versteckte Felder.
    for raw_id, raw_qty in zip(consumable_ids, consumable_quantities):
        try:
            consumable_id = uuid.UUID(raw_id)
            quantity = int(raw_qty)
        except ValueError:
            continue
        ok, message = await _try_reserve_consumable(session, user, worker, consumable_id, quantity)
        (succeeded if ok else failed).append(message)

    if not succeeded and not failed:
        return redirect_with_query("/reservations/cart", error="Warenkorb war leer.")

    ok_message = f"{len(succeeded)} Eintrag(e) reserviert." if succeeded else ""
    error_message = " / ".join(failed) if failed else ""
    return redirect_with_query("/reservations", ok=ok_message, error=error_message)


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


@router.post("/consumables/{reservation_id}/cancel")
async def cancel_consumable_reservation(
    reservation_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    reservation = await session.get(ConsumableReservation, reservation_id)
    if not reservation or not reservation.is_open:
        raise Forbidden()

    worker = await get_linked_worker(session, user)
    is_owner = worker and reservation.worker_id == worker.id
    if not is_owner and not user.is_admin:
        raise Forbidden()

    reservation.cancelled_at = utcnow()
    session.add(reservation)
    await session.commit()
    return RedirectResponse(url="/reservations?ok=Vormerkung+storniert.", status_code=303)
