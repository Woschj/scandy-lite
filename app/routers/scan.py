"""
Quickscan - der zentrale Werkstatt-Workflow: Barcode scannen (Gegenstand oder
Verbrauchsmaterial), Aktion bestätigen (ausleihen/zurückgeben/entnehmen),
fertig. Barcodes sind global eindeutig (DB-Constraint), daher kein
Abteilungs-Filter bei der Suche nötig - nur eine Berechtigungsprüfung danach.
"""
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import is_staff_in_department
from app.core.database import get_session
from app.core.deps import Forbidden, get_current_user, populate_nav_context, require_staff
from app.core.templating import templates
from app.models.common import ItemStatus, utcnow
from app.models.consumable import Consumable, ConsumableUsage
from app.models.item import Item
from app.models.lending import Lending
from app.models.user import User
from app.models.worker import Worker
from app.routers.reservations import get_open_reservation

router = APIRouter(prefix="/scan", tags=["scan"], dependencies=[Depends(populate_nav_context), Depends(require_staff)])


async def _check_department_access(session: AsyncSession, user: User, entity_department_id: uuid.UUID) -> None:
    """Nur wer in DIESER Abteilung Mitarbeiter-Rolle (oder Admin) hat, darf hier
    scannen - unabhängig davon, ob er in einer ANDEREN Abteilung Mitarbeiter ist."""
    if not await is_staff_in_department(session, user, entity_department_id):
        raise Forbidden()


@router.get("")
async def scan_home(
    request: Request,
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request, "scan/index.html",
        {"user": user, "ok": ok, "error": error},
    )


@router.post("/lookup")
async def scan_lookup(
    request: Request,
    barcode: str = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    barcode = barcode.strip()

    result = await session.exec(select(Item).where(Item.barcode == barcode, Item.deleted_at.is_(None)))
    item = result.first()
    if item:
        await _check_department_access(session, user, item.department_id)
        active_lending = None
        if item.status == ItemStatus.AUSGELIEHEN:
            lending_result = await session.exec(
                select(Lending)
                .where(Lending.item_id == item.id, Lending.returned_at.is_(None))
                .options(selectinload(Lending.worker))
            )
            active_lending = lending_result.first()
        reservation = await get_open_reservation(session, item.id)
        return templates.TemplateResponse(
            request, "scan/result.html",
            {
                "user": user, "kind": "item", "item": item,
                "lending": active_lending, "reservation": reservation,
            },
        )

    result = await session.exec(select(Consumable).where(Consumable.barcode == barcode, Consumable.deleted_at.is_(None)))
    consumable = result.first()
    if consumable:
        await _check_department_access(session, user, consumable.department_id)
        return templates.TemplateResponse(
            request, "scan/result.html",
            {"user": user, "kind": "consumable", "consumable": consumable},
        )

    return templates.TemplateResponse(
        request, "scan/result.html",
        {"user": user, "kind": "not_found", "barcode": barcode},
    )


@router.post("/lend")
async def scan_lend(
    item_id: uuid.UUID = Form(...),
    worker_barcode: str = Form(...),
    signature: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise Forbidden()
    await _check_department_access(session, user, item.department_id)

    if item.status != ItemStatus.VERFUEGBAR:
        return RedirectResponse(url="/scan?error=Gegenstand+ist+nicht+verfügbar.", status_code=303)

    # Unterschrift ist Pflicht (JS erzwingt sie clientseitig, hier serverseitig absichern).
    # Grobe Plausibilität: PNG-Data-URL, nicht absurd groß (Schutz vor Missbrauch als Datenspeicher).
    if not signature.startswith("data:image/png;base64,") or len(signature) > 200_000:
        return RedirectResponse(url="/scan?error=Unterschrift+fehlt+oder+ist+ungültig.", status_code=303)

    worker_result = await session.exec(
        select(Worker).where(Worker.barcode == worker_barcode.strip(), Worker.deleted_at.is_(None), Worker.is_active == True)  # noqa: E712
    )
    worker = worker_result.first()
    if not worker:
        return RedirectResponse(url="/scan?error=Mitarbeiter-Barcode+nicht+gefunden.", status_code=303)

    # Reservierungs-Logik: ist der Gegenstand für jemand ANDEREN reserviert -> blockieren.
    # Für DENSELBEN Worker reserviert -> Reservierung wird mit der Ausgabe erfüllt.
    reservation = await get_open_reservation(session, item.id)
    if reservation and reservation.worker_id != worker.id:
        reserved_name = reservation.worker.full_name if reservation.worker else "jemand anderen"
        return RedirectResponse(
            url=f"/scan?error=Gegenstand+ist+für+{reserved_name}+reserviert.", status_code=303
        )

    lending = Lending(
        item_id=item.id, worker_id=worker.id, department_id=item.department_id,
        signature=signature,
    )
    item.status = ItemStatus.AUSGELIEHEN
    if reservation:
        reservation.fulfilled_at = utcnow()
        session.add(reservation)
    session.add(lending)
    session.add(item)
    try:
        await session.commit()
    except IntegrityError:
        # Partial-Unique-Index (uq_lendings_open_item) hat zugeschlagen: jemand
        # war zwischen Anzeige und Bestätigung schneller. Sauber melden statt 500.
        await session.rollback()
        return RedirectResponse(url="/scan?error=Gegenstand+wurde+soeben+bereits+ausgeliehen.", status_code=303)

    return RedirectResponse(url=f"/scan?ok={item.name}+an+{worker.full_name}+ausgeliehen.", status_code=303)


@router.post("/return")
async def scan_return(
    item_id: uuid.UUID = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise Forbidden()
    await _check_department_access(session, user, item.department_id)

    lending_result = await session.exec(
        select(Lending).where(Lending.item_id == item.id, Lending.returned_at.is_(None))
    )
    lending = lending_result.first()
    if not lending:
        return RedirectResponse(url="/scan?error=Keine+offene+Ausleihe+gefunden.", status_code=303)

    lending.returned_at = utcnow()
    item.status = ItemStatus.VERFUEGBAR
    session.add(lending)
    session.add(item)
    await session.commit()

    return RedirectResponse(url=f"/scan?ok={item.name}+zurückgegeben.", status_code=303)


@router.post("/consume")
async def scan_consume(
    consumable_id: uuid.UUID = Form(...),
    quantity: int = Form(...),
    worker_barcode: str = Form(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    consumable = await session.get(Consumable, consumable_id)
    if not consumable or consumable.deleted_at is not None:
        raise Forbidden()
    await _check_department_access(session, user, consumable.department_id)

    if quantity <= 0:
        return RedirectResponse(url="/scan?error=Menge+muss+größer+als+0+sein.", status_code=303)
    if consumable.quantity < quantity:
        return RedirectResponse(url="/scan?error=Nicht+genug+Bestand+vorhanden.", status_code=303)

    worker_result = await session.exec(
        select(Worker).where(Worker.barcode == worker_barcode.strip(), Worker.deleted_at.is_(None), Worker.is_active == True)  # noqa: E712
    )
    worker = worker_result.first()
    if not worker:
        return RedirectResponse(url="/scan?error=Mitarbeiter-Barcode+nicht+gefunden.", status_code=303)

    consumable.quantity -= quantity
    usage = ConsumableUsage(consumable_id=consumable.id, worker_id=worker.id, quantity=quantity)
    session.add(consumable)
    session.add(usage)
    await session.commit()

    return RedirectResponse(
        url=f"/scan?ok={quantity}x+{consumable.name}+für+{worker.full_name}+entnommen.", status_code=303
    )
