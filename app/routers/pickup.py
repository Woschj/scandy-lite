"""
Sammel-Ausgabe für Reservierungen: eine Person hat mehrere Gegenstände
reserviert, Personal scannt sie beim Abholen nacheinander ab (statt jeden
einzeln über den normalen Scan-Workflow abzuwickeln). Fehlende Gegenstände
lassen sich aus der Abholung herausnehmen (Reservierung wird storniert,
nicht der ganze Vorgang abgebrochen). Am Ende EINE Unterschrift für alle
abgescannten Gegenstände zusammen.

Der "welche sind schon abgescannt"-Zustand ist bewusst NICHT serverseitig
gespeichert (keine eigene Tabelle nötig) - er wird als Liste von
Reservierungs-IDs durch die URL/Formulare der einzelnen Schritte
durchgereicht, bis am Ende die eigentlichen Lendings angelegt werden.
"""
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import is_staff_in_department
from app.core.database import get_session
from app.core.deps import Forbidden, get_current_department, get_current_user, populate_switchable_departments, require_staff
from app.core.templating import templates
from app.models.common import ItemStatus, utcnow
from app.models.department import Department
from app.models.item import Item
from app.models.lending import Lending
from app.models.reservation import Reservation
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(prefix="/scan/pickup", tags=["pickup"], dependencies=[Depends(populate_switchable_departments), Depends(require_staff)])


def _parse_checked(raw: str) -> list[uuid.UUID]:
    ids = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        try:
            ids.append(uuid.UUID(part))
        except ValueError:
            continue
    return ids


async def _open_reservations_for_worker(session: AsyncSession, worker_id: uuid.UUID) -> list[Reservation]:
    result = await session.exec(
        select(Reservation)
        .where(Reservation.worker_id == worker_id, Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
        .options(selectinload(Reservation.item))
        .order_by(Reservation.created_at)
    )
    return list(result.all())


@router.get("")
async def pickup_workers(
    request: Request,
    ok: str = "",
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    """Liste aller Personen mit mindestens einer offenen Gegenstands-
    Reservierung - Ausgangspunkt für die Sammel-Ausgabe."""
    stmt = (
        select(Reservation)
        .where(Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
        .options(selectinload(Reservation.worker))
    )
    if department:
        stmt = stmt.where(Reservation.department_id == department.id)
    reservations = (await session.exec(stmt)).all()

    workers_map: dict = {}
    for r in reservations:
        if r.worker and r.worker.id not in workers_map:
            workers_map[r.worker.id] = {"worker": r.worker, "count": 0}
        if r.worker:
            workers_map[r.worker.id]["count"] += 1
    workers_list = sorted(workers_map.values(), key=lambda w: w["worker"].last_name)

    return templates.TemplateResponse(
        request, "pickup/workers.html",
        {"user": user, "department": department, "workers_list": workers_list, "ok": ok},
    )


@router.get("/{worker_id}")
async def pickup_checklist(
    request: Request,
    worker_id: uuid.UUID,
    checked: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(Worker, worker_id)
    if not worker or worker.deleted_at is not None:
        raise Forbidden()

    reservations = await _open_reservations_for_worker(session, worker_id)
    checked_ids = set(_parse_checked(checked))

    pending, done = [], []
    for r in reservations:
        (done if r.id in checked_ids else pending).append(r)

    return templates.TemplateResponse(
        request, "pickup/checklist.html",
        {
            "user": user, "department": department, "worker": worker,
            "pending": pending, "done": done, "checked_param": checked, "error": error,
        },
    )


@router.post("/{worker_id}/scan")
async def pickup_scan(
    worker_id: uuid.UUID,
    barcode: str = Form(...),
    checked: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Scannt einen Gegenstand-Barcode und hakt ihn ab, falls er zu einer
    offenen Reservierung DIESER Person gehört."""
    checked_ids = _parse_checked(checked)

    item_result = await session.exec(select(Item).where(Item.barcode == barcode.strip(), Item.deleted_at.is_(None)))
    item = item_result.first()
    if not item:
        return RedirectResponse(
            url=f"/scan/pickup/{worker_id}?checked={checked}&error=Barcode+nicht+gefunden.", status_code=303
        )

    if not await is_staff_in_department(session, user, item.department_id):
        raise Forbidden()

    reservations = await _open_reservations_for_worker(session, worker_id)
    match = next((r for r in reservations if r.item_id == item.id), None)
    if not match:
        return RedirectResponse(
            url=f"/scan/pickup/{worker_id}?checked={checked}&error={item.name}+ist+für+diese+Person+nicht+reserviert.",
            status_code=303,
        )

    if match.id not in checked_ids:
        checked_ids.append(match.id)

    new_checked = ",".join(str(i) for i in checked_ids)
    return RedirectResponse(url=f"/scan/pickup/{worker_id}?checked={new_checked}", status_code=303)


@router.post("/{worker_id}/remove/{reservation_id}")
async def pickup_remove(
    worker_id: uuid.UUID,
    reservation_id: uuid.UUID,
    checked: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """Nimmt einen fehlenden Gegenstand aus der Abholung heraus - storniert
    NUR diese eine Reservierung, der Rest der Abholung läuft normal weiter."""
    reservation = await session.get(Reservation, reservation_id)
    if not reservation or not reservation.is_open or reservation.worker_id != worker_id:
        raise Forbidden()

    if not await is_staff_in_department(session, user, reservation.department_id):
        raise Forbidden()

    reservation.cancelled_at = utcnow()
    session.add(reservation)
    await session.commit()

    # Diese ID aus der checked-Liste entfernen, falls sie (theoretisch) dort
    # gestanden hätte - kann nicht passieren, da entfernen nur bei "pending"
    # angeboten wird, aber zur Robustheit trotzdem sauber rausfiltern.
    checked_ids = [i for i in _parse_checked(checked) if i != reservation_id]
    return RedirectResponse(url=f"/scan/pickup/{worker_id}?checked={','.join(str(i) for i in checked_ids)}", status_code=303)


@router.post("/{worker_id}/confirm")
async def pickup_confirm(
    worker_id: uuid.UUID,
    checked: str = Form(""),
    signature: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(Worker, worker_id)
    if not worker or worker.deleted_at is not None:
        raise Forbidden()

    checked_ids = _parse_checked(checked)
    if not checked_ids:
        return RedirectResponse(url=f"/scan/pickup/{worker_id}?error=Kein+Gegenstand+abgehakt.", status_code=303)

    if not signature.startswith("data:image/png;base64,") or len(signature) > 200_000:
        return RedirectResponse(
            url=f"/scan/pickup/{worker_id}?checked={checked}&error=Unterschrift+fehlt+oder+ist+ungültig.", status_code=303
        )

    reservations = await _open_reservations_for_worker(session, worker_id)
    to_fulfill = [r for r in reservations if r.id in checked_ids]
    if not to_fulfill:
        return RedirectResponse(url=f"/scan/pickup/{worker_id}?error=Nichts+mehr+abzugeben+-+bitte+erneut+prüfen.", status_code=303)

    for reservation in to_fulfill:
        if not await is_staff_in_department(session, user, reservation.department_id):
            raise Forbidden()

    count = 0
    for reservation in to_fulfill:
        item = await session.get(Item, reservation.item_id)
        if not item or item.status != ItemStatus.VERFUEGBAR:
            continue  # zwischenzeitlich anderweitig ausgeliehen o.ä. - überspringen statt hart abzubrechen
        lending = Lending(
            item_id=item.id, worker_id=worker.id, department_id=reservation.department_id, signature=signature,
        )
        item.status = ItemStatus.AUSGELIEHEN
        reservation.fulfilled_at = utcnow()
        session.add(lending)
        session.add(item)
        session.add(reservation)
        count += 1

    await session.commit()
    return RedirectResponse(
        url=f"/scan/pickup?ok={count}+Gegenstand(e)+an+{worker.full_name}+ausgegeben.", status_code=303
    )
