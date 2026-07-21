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
import logging
import uuid

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_department_roles, is_staff_in_department
from app.core.database import get_session
from app.core.deps import Forbidden, get_current_user, populate_nav_context, require_staff, verify_csrf
from app.core.responses import redirect_with_query
from app.core.templating import templates
from app.models.common import ItemStatus, UserRole, utcnow
from app.models.item import Item
from app.models.lending import Lending
from app.models.reservation import Reservation
from app.models.user import User

router = APIRouter(prefix="/scan/pickup", tags=["pickup"], dependencies=[Depends(populate_nav_context), Depends(require_staff), Depends(verify_csrf)])
logger = logging.getLogger("scandy-lite")


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


async def get_open_reservations_for_worker(session: AsyncSession, worker_id: uuid.UUID) -> list[Reservation]:
    """Bewusst nicht unterstrichen (anders als _parse_checked) - wird auch von
    app.routers.scan.scan_lookup importiert, um beim Scannen eines Mitarbeiter-
    Barcodes zu prüfen, ob eine Weiterleitung zur Sammel-Ausgabe sinnvoll ist."""
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
    session: AsyncSession = Depends(get_session),
):
    """Liste aller Personen mit mindestens einer offenen Gegenstands-
    Reservierung - Ausgangspunkt für die Sammel-Ausgabe. Zeigt alle
    Abteilungen, in denen dieser User Mitarbeiter-Rolle hat, gemischt
    (Admin: wirklich alle)."""
    stmt = (
        select(Reservation)
        .where(Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
        .options(selectinload(Reservation.worker))
    )
    if not user.is_admin:
        roles = await get_department_roles(session, user)
        staff_dept_ids = [r.department_id for r in roles if r.role == UserRole.MITARBEITER]
        stmt = stmt.where(Reservation.department_id.in_(staff_dept_ids))
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
        {"user": user, "workers_list": workers_list, "ok": ok},
    )


@router.get("/{worker_id}")
async def pickup_checklist(
    request: Request,
    worker_id: uuid.UUID,
    checked: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(User, worker_id)
    if not worker or worker.deleted_at is not None:
        raise Forbidden()

    reservations = await get_open_reservations_for_worker(session, worker_id)
    checked_ids = set(_parse_checked(checked))

    pending, done = [], []
    for r in reservations:
        (done if r.id in checked_ids else pending).append(r)

    return templates.TemplateResponse(
        request, "pickup/checklist.html",
        {
            "user": user, "worker": worker,
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
        return redirect_with_query(f"/scan/pickup/{worker_id}", checked=checked, error="Barcode nicht gefunden.")

    if not await is_staff_in_department(session, user, item.department_id):
        raise Forbidden()

    reservations = await get_open_reservations_for_worker(session, worker_id)
    match = next((r for r in reservations if r.item_id == item.id), None)
    if not match:
        return redirect_with_query(
            f"/scan/pickup/{worker_id}", checked=checked, error=f"{item.name} ist für diese Person nicht reserviert."
        )

    if match.id not in checked_ids:
        checked_ids.append(match.id)

    new_checked = ",".join(str(i) for i in checked_ids)
    return redirect_with_query(f"/scan/pickup/{worker_id}", checked=new_checked)


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
    return redirect_with_query(f"/scan/pickup/{worker_id}", checked=",".join(str(i) for i in checked_ids))


@router.post("/{worker_id}/confirm")
async def pickup_confirm(
    worker_id: uuid.UUID,
    checked: str = Form(""),
    signature: str = Form(""),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    worker = await session.get(User, worker_id)
    if not worker or worker.deleted_at is not None:
        raise Forbidden()

    checked_ids = _parse_checked(checked)
    if not checked_ids:
        return redirect_with_query(f"/scan/pickup/{worker_id}", error="Kein Gegenstand abgehakt.")

    if not signature.startswith("data:image/png;base64,") or len(signature) > 200_000:
        return redirect_with_query(
            f"/scan/pickup/{worker_id}", checked=checked, error="Unterschrift fehlt oder ist ungültig."
        )

    reservations = await get_open_reservations_for_worker(session, worker_id)
    to_fulfill = [r for r in reservations if r.id in checked_ids]
    if not to_fulfill:
        return redirect_with_query(f"/scan/pickup/{worker_id}", error="Nichts mehr abzugeben - bitte erneut prüfen.")

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

    try:
        await session.commit()
    except IntegrityError:
        # Partial-Unique-Index (uq_lendings_open_item) hat zugeschlagen: einer
        # der geprüften Gegenstände wurde zwischen der Status-Prüfung oben und
        # diesem Commit über einen anderen Weg (normaler Scan-Workflow)
        # ausgeliehen. Sauber melden statt die ganze Charge mit einem
        # unbehandelten 500er zu verlieren - gleiches Muster wie scan.py scan_lend.
        await session.rollback()
        logger.warning("Sammel-Ausgabe an Worker %s kollidierte mit einer gleichzeitigen Ausleihe.", worker_id)
        return redirect_with_query(
            f"/scan/pickup/{worker_id}",
            error="Mindestens ein Gegenstand wurde zwischenzeitlich anderweitig ausgeliehen - bitte erneut prüfen.",
        )
    return redirect_with_query("/scan/pickup", ok=f"{count} Gegenstand(e) an {worker.full_name} ausgegeben.")
