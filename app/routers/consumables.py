"""
CRUD für Verbrauchsmaterial + Bestandsanpassung. Eine Entnahme mit gewähltem
Mitarbeiter wird als ConsumableUsage protokolliert (Grundlage der Historie);
reiner Nachschub (kein Mitarbeiter gewählt) verändert nur den Bestand.

Abteilungsgescoped über UserDepartmentRole - siehe items.py für die
ausführliche Erklärung des Berechtigungsmodells, hier identisch angewendet.
Kein "aktuell aktive Abteilung"-Kontext (kein Umschalter).
"""
import logging
import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select, update
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_department_roles, get_visible_department_ids, is_staff_in_department
from app.core.barcodes import barcode_taken_by_other_kind
from app.core.database import get_session
from app.core.deps import Forbidden, get_current_user, populate_nav_context, require_staff, verify_csrf
from app.core.inventory_crud import (
    HISTORY_LIMIT,
    InventoryKind,
    delete_entity,
    delete_entity_image,
    presets,
    presets_by_department,
    staff_departments,
    upload_entity_image,
)
from app.core.templating import templates
from app.models.common import UserRole
from app.models.consumable import Consumable, ConsumableUsage
from app.models.user import User

router = APIRouter(prefix="/consumables", tags=["consumables"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])
logger = logging.getLogger("scandy-lite")

CONSUMABLE_KIND = InventoryKind(model=Consumable, url_prefix="consumables")


CONSUMABLE_AVAILABILITY_RANK = case((Consumable.quantity > 0, 0), else_=1)
CONSUMABLE_SORT_COLUMNS = {
    "status": (CONSUMABLE_AVAILABILITY_RANK, Consumable.name),
    "name": (Consumable.name,),
    "barcode": (Consumable.barcode,),
    "quantity": (Consumable.quantity,),
}

_PAGE_SIZE = 60  # an die Kachel-/Listenansicht angepasst


@router.get("")
async def list_consumables(
    request: Request,
    q: str = "",
    status: str = "",
    category: str = "",
    location: str = "",
    sort: str = "status",
    page: int = 1,
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from app.routers.reservations import get_linked_worker

    # page=0 oder negativ (z.B. per manipuliertem Query-Parameter) würde sonst
    # über Pythons negative Slice-Indizierung ein falsches/leeres Ergebnis
    # liefern statt auf Seite 1 zu klemmen (siehe history.py).
    page = max(page, 1)

    linked_worker = await get_linked_worker(session, user)
    has_any_staff_role = getattr(request.state, "has_any_staff_role", False)

    stmt = (
        select(Consumable)
        .where(Consumable.deleted_at.is_(None))
        .order_by(*CONSUMABLE_SORT_COLUMNS.get(sort, CONSUMABLE_SORT_COLUMNS["status"]))
        .options(selectinload(Consumable.department))
    )

    staff_department_ids: set = set()
    visible_ids = None
    if not user.is_admin:
        roles = await get_department_roles(session, user)
        staff_department_ids = {r.department_id for r in roles if r.role == UserRole.MITARBEITER}
        visible_ids = await get_visible_department_ids(session, user)
        stmt = stmt.where(Consumable.department_id.in_(visible_ids))

    if q:
        like = f"%{q}%"
        stmt = stmt.where((Consumable.name.ilike(like)) | (Consumable.barcode.ilike(like)))

    if status == "verfuegbar":
        stmt = stmt.where(Consumable.quantity > 0)
    elif status in ("leer", "nicht_verfuegbar"):
        stmt = stmt.where(Consumable.quantity == 0)
    elif status == "mindestbestand":
        if user.is_admin:
            stmt = stmt.where(Consumable.quantity <= Consumable.min_quantity)
        else:
            # WICHTIG: abteilungsspezifisch, nicht global (siehe items.py -
            # ein globales has_any_staff_role-Flag hätte einem User, der nur
            # in EINER Abteilung Mitarbeiter ist, erlaubt, den Mindestbestand-
            # Filter fälschlich auch für Abteilungen zu nutzen, in denen er
            # nur Nutzer-Rolle hat). Für nicht-Mitarbeiter-Abteilungen liefert
            # der Filter schlicht keine Treffer, statt den Hinweis zu leaken.
            stmt = stmt.where(
                Consumable.department_id.in_(staff_department_ids) & (Consumable.quantity <= Consumable.min_quantity)
            )
    # status == "mindestbestand": der Hinweis ist "firmeninterna" und darf
    # auch über die URL nicht abteilungsübergreifend filterbar sein.
    if category:
        stmt = stmt.where(Consumable.category == category)
    if location:
        stmt = stmt.where(Consumable.location == location)

    # Ein Element mehr als die Seitengröße abfragen statt einer separaten
    # COUNT-Query, um zu wissen, ob eine weitere Seite existiert (has_more).
    stmt = stmt.offset((page - 1) * _PAGE_SIZE).limit(_PAGE_SIZE + 1)
    result = await session.exec(stmt)
    consumables = result.all()
    has_more = len(consumables) > _PAGE_SIZE
    consumables = consumables[:_PAGE_SIZE]

    category_stmt = select(Consumable.category).where(Consumable.deleted_at.is_(None), Consumable.category.is_not(None)).distinct()
    location_stmt = select(Consumable.location).where(Consumable.deleted_at.is_(None), Consumable.location.is_not(None)).distinct()
    if not user.is_admin:
        category_stmt = category_stmt.where(Consumable.department_id.in_(visible_ids))
        location_stmt = location_stmt.where(Consumable.department_id.in_(visible_ids))
    available_categories = sorted((await session.exec(category_stmt)).all())
    available_locations = sorted((await session.exec(location_stmt)).all())

    return templates.TemplateResponse(
        request,
        "consumables/list.html",
        {
            "user": user, "consumables": consumables, "q": q, "ok": ok, "error": error,
            "status": status, "category": category, "location": location, "sort": sort,
            "available_categories": available_categories, "available_locations": available_locations,
            "linked_worker": linked_worker, "staff_department_ids": staff_department_ids,
            "has_any_staff_role": has_any_staff_role,
            "page": page, "has_more": has_more,
        },
    )


@router.get("/new")
async def new_consumable_form(
    request: Request,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    departments = await staff_departments(session, user)
    if not departments:
        raise Forbidden()

    categories_by_department, locations_by_department = await presets_by_department(session, [d.id for d in departments])
    return templates.TemplateResponse(
        request,
        "consumables/form.html",
        {
            "user": user, "consumable": None, "error": None,
            "departments": departments,
            "categories_by_department": categories_by_department,
            "locations_by_department": locations_by_department,
        },
    )


@router.post("/new")
async def create_consumable(
    request: Request,
    barcode: str = Form(...),
    name: str = Form(...),
    department_id: uuid.UUID = Form(...),
    category: str = Form(""),
    location: str = Form(""),
    unit: str = Form("Stück"),
    quantity: int = Form(0),
    min_quantity: int = Form(0),
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    if not await is_staff_in_department(session, user, department_id):
        raise Forbidden()

    result = await session.exec(
        select(Consumable).where(Consumable.barcode == barcode, Consumable.deleted_at.is_(None))
    )
    if result.first() or await barcode_taken_by_other_kind(session, barcode, kind="consumable"):
        departments = await staff_departments(session, user)
        categories_by_department, locations_by_department = await presets_by_department(session, [d.id for d in departments])
        return templates.TemplateResponse(
            request,
            "consumables/form.html",
            {
                "user": user, "consumable": None,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "departments": departments,
                "categories_by_department": categories_by_department,
                "locations_by_department": locations_by_department,
                "selected_department_id": department_id,
            },
            status_code=409,
        )

    consumable = Consumable(
        barcode=barcode, name=name, category=category or None, location=location or None,
        unit=unit or "Stück", quantity=max(quantity, 0), min_quantity=max(min_quantity, 0),
        department_id=department_id,
    )
    session.add(consumable)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning("Anlegen von Verbrauchsmaterial mit Barcode '%s' kollidierte mit einer gleichzeitigen Anlage.", barcode)
        return RedirectResponse(url="/consumables?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/consumables", status_code=303)


@router.get("/{consumable_id}")
async def consumable_detail(
    request: Request,
    consumable_id: uuid.UUID,
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from app.routers.reservations import get_linked_worker

    result = await session.exec(
        select(Consumable)
        .where(Consumable.id == consumable_id, Consumable.deleted_at.is_(None))
        .options(selectinload(Consumable.department))
    )
    consumable = result.first()
    if not consumable:
        raise Forbidden()

    if not user.is_admin:
        visible_ids = await get_visible_department_ids(session, user)
        if consumable.department_id not in visible_ids:
            raise Forbidden()

    can_manage = await is_staff_in_department(session, user, consumable.department_id)
    linked_worker = await get_linked_worker(session, user)

    # Kompakte Entnahme-Historie DIESES Verbrauchsmaterials - beantwortet
    # "wer hat wie viel bekommen" bereits als chronologische Liste (jede
    # Zeile zeigt Person + Menge), ohne eine separate Gruppierungs-Query.
    usage_history = []
    if can_manage:
        usage_history = (
            await session.exec(
                select(ConsumableUsage)
                .where(ConsumableUsage.consumable_id == consumable.id)
                .options(selectinload(ConsumableUsage.worker))
                .order_by(ConsumableUsage.used_at.desc())
                .limit(HISTORY_LIMIT)
            )
        ).all()

    return templates.TemplateResponse(
        request,
        "consumables/detail.html",
        {
            "user": user, "consumable": consumable, "ok": ok, "error": error,
            "can_manage": can_manage, "linked_worker": linked_worker,
            "usage_history": usage_history,
        },
    )


@router.get("/{consumable_id}/edit")
async def edit_consumable_form(
    request: Request,
    consumable_id: uuid.UUID,
    ok: str = "",
    error: str = "",
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    consumable = await session.get(Consumable, consumable_id)
    if not consumable or consumable.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, consumable.department_id):
        raise Forbidden()

    categories, locations = await presets(session, consumable.department_id)
    return templates.TemplateResponse(
        request,
        "consumables/form.html",
        {
            "user": user, "consumable": consumable, "error": error, "ok": ok,
            "categories": categories, "locations": locations,
        },
    )


@router.post("/{consumable_id}/edit")
async def update_consumable(
    request: Request,
    consumable_id: uuid.UUID,
    barcode: str = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    location: str = Form(""),
    unit: str = Form("Stück"),
    min_quantity: int = Form(0),
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    consumable = await session.get(Consumable, consumable_id)
    if not consumable or consumable.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, consumable.department_id):
        raise Forbidden()

    result = await session.exec(
        select(Consumable).where(
            Consumable.barcode == barcode, Consumable.id != consumable_id, Consumable.deleted_at.is_(None)
        )
    )
    if result.first() or await barcode_taken_by_other_kind(session, barcode, kind="consumable"):
        categories, locations = await presets(session, consumable.department_id)
        return templates.TemplateResponse(
            request,
            "consumables/form.html",
            {
                "user": user, "consumable": consumable,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "categories": categories, "locations": locations,
            },
            status_code=409,
        )

    consumable.barcode = barcode
    consumable.name = name
    consumable.category = category or None
    consumable.location = location or None
    consumable.unit = unit or "Stück"
    consumable.min_quantity = max(min_quantity, 0)
    session.add(consumable)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning("Aktualisieren von Verbrauchsmaterial %s kollidierte mit einer gleichzeitigen Änderung (Barcode '%s').", consumable.id, barcode)
        return RedirectResponse(url="/consumables?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/consumables", status_code=303)


@router.post("/{consumable_id}/adjust")
async def adjust_consumable(
    consumable_id: uuid.UUID,
    delta: int = Form(...),
    worker_id: str = Form(""),
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    consumable = await session.get(Consumable, consumable_id)
    if not consumable or consumable.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, consumable.department_id):
        raise Forbidden()

    # Atomares UPDATE mit Bestands-Guard in der WHERE-Klausel statt
    # check-then-write: verhindert, dass zwei gleichzeitige Anpassungen
    # denselben Bestand negativ werden lassen.
    update_result = await session.exec(
        update(Consumable)
        .where(Consumable.id == consumable.id, Consumable.quantity + delta >= 0)
        .values(quantity=Consumable.quantity + delta)
        .returning(Consumable.quantity)
    )
    if update_result.first() is None:
        await session.rollback()
        raise Forbidden()  # kein negativer Bestand - kein stiller Fehlerfall, sondern harter Stop

    # Entnahme (delta < 0) mit gewähltem Mitarbeiter protokollieren -> Historie
    if delta < 0 and worker_id:
        try:
            parsed_worker_id = uuid.UUID(worker_id)
        except ValueError:
            raise Forbidden()  # manipulierte Form-Daten - kein stiller 500er
        usage = ConsumableUsage(
            consumable_id=consumable.id,
            worker_id=parsed_worker_id,
            quantity=abs(delta),
            department_id=consumable.department_id,
        )
        session.add(usage)

    await session.commit()
    return RedirectResponse(url="/consumables", status_code=303)


@router.post("/{consumable_id}/delete")
async def delete_consumable(
    consumable_id: uuid.UUID,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    return await delete_entity(session, CONSUMABLE_KIND, consumable_id, user)


@router.post("/{consumable_id}/image")
async def upload_consumable_image(
    consumable_id: uuid.UUID,
    image: UploadFile,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    return await upload_entity_image(session, CONSUMABLE_KIND, consumable_id, image, user)


@router.post("/{consumable_id}/image/delete")
async def delete_consumable_image(
    consumable_id: uuid.UUID,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    return await delete_entity_image(session, CONSUMABLE_KIND, consumable_id, user)
