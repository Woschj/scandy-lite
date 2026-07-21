"""
CRUD für Gegenstände (Items). Abteilungsgescoped über UserDepartmentRole:
Sichtbarkeit richtet sich danach, in welchen Abteilungen ein User überhaupt
eine Rolle hat; Verwalten (Anlegen/Bearbeiten/Löschen) erfordert zusätzlich
die Mitarbeiter-Rolle SPEZIFISCH in der jeweiligen Abteilung.

Kein "aktuell aktive Abteilung"-Kontext (kein Umschalter) - die Liste zeigt
immer alles Sichtbare gemischt (mit Abteilungs-Badge pro Karte), und beim
Anlegen ist die Abteilung ein normales Formularfeld.
"""
import logging
import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import case
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_department_roles, get_visible_department_ids, is_staff_in_department
from app.core.barcodes import barcode_taken_by_other_kind
from app.core.custom_fields import (
    get_definitions_by_category,
    get_definitions_by_department_and_category,
    get_definitions_for_item,
    get_values_for_item,
    save_values_for_item,
)
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
from app.models.common import ItemStatus, UserRole
from app.models.item import Item
from app.models.lending import Lending
from app.models.user import User

router = APIRouter(prefix="/items", tags=["items"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])
logger = logging.getLogger("scandy-lite")

ITEM_KIND = InventoryKind(model=Item, url_prefix="items")


# "status"-Sortierung bedeutet NICHT alphabetisch nach dem rohen Enum-String
# (da käme "ausgeliehen" vor "verfuegbar") - stattdessen "verfügbar zuerst,
# dann alphabetisch nach Name". Default-Sortierung der Liste.
ITEM_AVAILABILITY_RANK = case((Item.status == ItemStatus.VERFUEGBAR, 0), else_=1)
ITEM_SORT_COLUMNS = {
    "status": (ITEM_AVAILABILITY_RANK, Item.name),
    "name": (Item.name,),
    "barcode": (Item.barcode,),
}

_PAGE_SIZE = 60  # an die Kachel-/Listenansicht angepasst


@router.get("")
async def list_items(
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
    from app.models.reservation import Reservation
    from app.routers.reservations import get_linked_worker

    # page=0 oder negativ (z.B. per manipuliertem Query-Parameter) würde sonst
    # über Pythons negative Slice-Indizierung ein falsches/leeres Ergebnis
    # liefern statt auf Seite 1 zu klemmen (siehe history.py).
    page = max(page, 1)

    linked_worker = await get_linked_worker(session, user)
    has_any_staff_role = getattr(request.state, "has_any_staff_role", False)

    stmt = (
        select(Item)
        .where(Item.deleted_at.is_(None))
        .order_by(*ITEM_SORT_COLUMNS.get(sort, ITEM_SORT_COLUMNS["status"]))
        .options(selectinload(Item.department))
    )

    staff_department_ids: set = set()
    if user.is_admin:
        visible_ids = None
    else:
        roles = await get_department_roles(session, user)
        staff_department_ids = {r.department_id for r in roles if r.role == UserRole.MITARBEITER}
        visible_ids = await get_visible_department_ids(session, user)
        stmt = stmt.where(Item.department_id.in_(visible_ids))

    if q:
        like = f"%{q}%"
        stmt = stmt.where((Item.name.ilike(like)) | (Item.barcode.ilike(like)))

    if status == "nicht_verfuegbar":
        stmt = stmt.where(Item.status != ItemStatus.VERFUEGBAR)
    elif status in ("ausgeliehen", "defekt", "ausgemustert"):
        try:
            target_status = ItemStatus(status)
        except ValueError:
            target_status = None
        if target_status is not None:
            if user.is_admin:
                stmt = stmt.where(Item.status == target_status)
            else:
                # Genauer Grund ("firmeninterna") ist fuer reine Nutzer-Rolle
                # nicht sichtbar/filterbar - WICHTIG: das muss ABTEILUNGS-
                # SPEZIFISCH gelten, nicht global. Ein User kann Mitarbeiter
                # in Abteilung A und nur Nutzer in Abteilung B sein - ein
                # globales "hat irgendwo Mitarbeiter-Rolle"-Flag (frueherer
                # Bug) haette diesem User erlaubt, den granularen Filter auch
                # fuer Abteilung B zu nutzen. Deshalb hier: granularer Filter
                # nur innerhalb von staff_department_ids, in allen anderen
                # sichtbaren Abteilungen auf die binaere Grenze heruntergestuft.
                stmt = stmt.where(
                    (Item.department_id.in_(staff_department_ids) & (Item.status == target_status))
                    | (Item.department_id.not_in(staff_department_ids) & (Item.status != ItemStatus.VERFUEGBAR))
                )
    elif status:
        try:
            stmt = stmt.where(Item.status == ItemStatus(status))
        except ValueError:
            pass  # ungültiger Wert (z.B. manipulierte URL) - Filter einfach ignorieren statt 500er
    if category:
        stmt = stmt.where(Item.category == category)
    if location:
        stmt = stmt.where(Item.location == location)

    # Ein Element mehr als die Seitengröße abfragen statt einer separaten
    # COUNT-Query, um zu wissen, ob eine weitere Seite existiert (has_more).
    stmt = stmt.offset((page - 1) * _PAGE_SIZE).limit(_PAGE_SIZE + 1)
    result = await session.exec(stmt)
    items = result.all()
    has_more = len(items) > _PAGE_SIZE
    items = items[:_PAGE_SIZE]

    # Kategorie-/Standort-Werte fürs Filter-Dropdown: unabhängig von den
    # aktuell gesetzten Filtern/der Suche, damit Optionen nicht verschwinden,
    # sobald ein anderer Filter aktiv ist - nur an dieselbe Abteilungs-
    # Sichtbarkeit gebunden wie die Liste selbst.
    category_stmt = select(Item.category).where(Item.deleted_at.is_(None), Item.category.is_not(None)).distinct()
    location_stmt = select(Item.location).where(Item.deleted_at.is_(None), Item.location.is_not(None)).distinct()
    if not user.is_admin:
        category_stmt = category_stmt.where(Item.department_id.in_(visible_ids))
        location_stmt = location_stmt.where(Item.department_id.in_(visible_ids))
    available_categories = sorted((await session.exec(category_stmt)).all())
    available_locations = sorted((await session.exec(location_stmt)).all())

    # Offene Reservierungen der angezeigten Items (für "Reserviert"-Chip + Button-Logik)
    reserved_ids: set = set()
    if items:
        res_result = await session.exec(
            select(Reservation.item_id).where(
                Reservation.item_id.in_([i.id for i in items]),
                Reservation.fulfilled_at.is_(None),
                Reservation.cancelled_at.is_(None),
            )
        )
        reserved_ids = set(res_result.all())

    return templates.TemplateResponse(
        request,
        "items/list.html",
        {
            "user": user, "items": items, "q": q, "ok": ok, "error": error,
            "status": status, "category": category, "location": location, "sort": sort,
            "available_categories": available_categories, "available_locations": available_locations,
            "reserved_ids": reserved_ids, "linked_worker": linked_worker,
            "staff_department_ids": staff_department_ids, "has_any_staff_role": has_any_staff_role,
            "page": page, "has_more": has_more,
        },
    )


@router.get("/new")
async def new_item_form(
    request: Request,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    departments = await staff_departments(session, user)
    if not departments:
        raise Forbidden()  # keine Abteilung, in der dieser User Mitarbeiter-Rolle hat

    categories_by_department, locations_by_department = await presets_by_department(session, [d.id for d in departments])
    custom_fields_by_department_category = await get_definitions_by_department_and_category(session, [d.id for d in departments])
    return templates.TemplateResponse(
        request,
        "items/form.html",
        {
            "user": user, "item": None, "error": None,
            "departments": departments,
            "categories_by_department": categories_by_department,
            "locations_by_department": locations_by_department,
            "custom_fields_by_department_category": custom_fields_by_department_category,
        },
    )


@router.post("/new")
async def create_item(
    request: Request,
    barcode: str = Form(...),
    name: str = Form(...),
    department_id: uuid.UUID = Form(...),
    category: str = Form(""),
    location: str = Form(""),
    notes: str = Form(""),
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    if not await is_staff_in_department(session, user, department_id):
        raise Forbidden()

    result = await session.exec(select(Item).where(Item.barcode == barcode, Item.deleted_at.is_(None)))
    if result.first() or await barcode_taken_by_other_kind(session, barcode, kind="item"):
        departments = await staff_departments(session, user)
        categories_by_department, locations_by_department = await presets_by_department(session, [d.id for d in departments])
        custom_fields_by_department_category = await get_definitions_by_department_and_category(session, [d.id for d in departments])
        return templates.TemplateResponse(
            request,
            "items/form.html",
            {
                "user": user, "item": None,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "departments": departments,
                "categories_by_department": categories_by_department,
                "locations_by_department": locations_by_department,
                "custom_fields_by_department_category": custom_fields_by_department_category,
                "selected_department_id": department_id,
            },
            status_code=409,
        )

    item = Item(
        barcode=barcode, name=name,
        category=category or None, location=location or None, notes=notes or None,
        department_id=department_id,
    )
    session.add(item)
    try:
        # Flush BEVOR die Zusatzfeld-Werte angelegt werden: ohne eine explizite
        # SQLModel-Relationship zwischen Item und CustomFieldValue sortiert
        # SQLAlchemy die INSERTs beim finalen Commit nicht zuverlässig nach
        # Fremdschlüssel-Abhängigkeit - der Gegenstand muss in der DB existieren,
        # bevor eine CustomFieldValue-Zeile mit derselben item_id eingefügt wird
        # (sonst Fremdschlüssel-Verletzung, siehe Regressionstest in
        # tests/test_custom_fields.py). Der Flush kann theoretisch selbst an
        # der Barcode-Eindeutigkeit scheitern (Race mit der SELECT-Prüfung
        # oben) - deshalb hier schon abgesichert, nicht erst beim Commit.
        await session.flush()
    except IntegrityError:
        await session.rollback()
        logger.warning("Anlegen von Gegenstand mit Barcode '%s' kollidierte mit einer gleichzeitigen Anlage.", barcode)
        return RedirectResponse(url="/items?error=Barcode+ist+bereits+vergeben.", status_code=303)

    form_data = await request.form()
    custom_field_errors = await save_values_for_item(session, item, form_data)
    if custom_field_errors:
        departments = await staff_departments(session, user)
        categories_by_department, locations_by_department = await presets_by_department(session, [d.id for d in departments])
        custom_fields_by_department_category = await get_definitions_by_department_and_category(session, [d.id for d in departments])
        return templates.TemplateResponse(
            request,
            "items/form.html",
            {
                "user": user, "item": None,
                "error": " ".join(custom_field_errors),
                "departments": departments,
                "categories_by_department": categories_by_department,
                "locations_by_department": locations_by_department,
                "custom_fields_by_department_category": custom_fields_by_department_category,
                "selected_department_id": department_id,
            },
            status_code=400,
        )

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning("Anlegen von Gegenstand mit Barcode '%s' kollidierte mit einer gleichzeitigen Anlage (Custom-Field-Commit).", barcode)
        return RedirectResponse(url="/items?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/items", status_code=303)


@router.get("/{item_id}")
async def item_detail(
    request: Request,
    item_id: uuid.UUID,
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from app.models.reservation import Reservation
    from app.routers.reservations import get_linked_worker

    result = await session.exec(
        select(Item).where(Item.id == item_id, Item.deleted_at.is_(None)).options(selectinload(Item.department))
    )
    item = result.first()
    if not item:
        raise Forbidden()

    if not user.is_admin:
        visible_ids = await get_visible_department_ids(session, user)
        if item.department_id not in visible_ids:
            raise Forbidden()

    can_manage = await is_staff_in_department(session, user, item.department_id)
    linked_worker = await get_linked_worker(session, user)

    reservation = (
        await session.exec(
            select(Reservation)
            .where(Reservation.item_id == item.id, Reservation.fulfilled_at.is_(None), Reservation.cancelled_at.is_(None))
            .options(selectinload(Reservation.worker))
        )
    ).first()

    active_lending = None
    if can_manage and item.status == ItemStatus.AUSGELIEHEN:
        active_lending = (
            await session.exec(
                select(Lending)
                .where(Lending.item_id == item.id, Lending.returned_at.is_(None))
                .options(selectinload(Lending.worker))
            )
        ).first()

    # Zusatzfelder: nur die mit tatsächlich gesetztem Wert, zusätzlich auf
    # visible_to_all beschränkt für alle ohne can_manage - dieselbe Regel wie
    # bei Status/Mindestbestand, aber pro Feld statt pauschal (siehe
    # app/models/custom_field.py).
    field_definitions = await get_definitions_for_item(session, item)
    field_values = await get_values_for_item(session, item.id)
    custom_fields = [
        (f, field_values[f.id])
        for f in field_definitions
        if field_values.get(f.id) and (can_manage or f.visible_to_all)
    ]

    # Kompakte Ausleih-Historie DIESES Gegenstands - nur für Verwaltende
    # (dieselbe Sichtbarkeitsregel wie active_lending oben), Verweis auf die
    # vollständige, durchsuchbare Historie über die bestehende Freitextsuche
    # in app/routers/history.py statt eine eigene Filter-Query zu bauen.
    lending_history = []
    if can_manage:
        lending_history = (
            await session.exec(
                select(Lending)
                .where(Lending.item_id == item.id)
                .options(selectinload(Lending.worker))
                .order_by(Lending.lent_at.desc())
                .limit(HISTORY_LIMIT)
            )
        ).all()

    return templates.TemplateResponse(
        request,
        "items/detail.html",
        {
            "user": user, "item": item, "ok": ok, "error": error,
            "can_manage": can_manage, "linked_worker": linked_worker,
            "reservation": reservation, "active_lending": active_lending,
            "custom_fields": custom_fields, "lending_history": lending_history,
        },
    )


@router.get("/{item_id}/edit")
async def edit_item_form(
    request: Request,
    item_id: uuid.UUID,
    ok: str = "",
    error: str = "",
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, item.department_id):
        raise Forbidden()

    categories, locations = await presets(session, item.department_id)
    custom_fields_by_category = await get_definitions_by_category(session, item.department_id)
    custom_field_values = await get_values_for_item(session, item.id)
    return templates.TemplateResponse(
        request,
        "items/form.html",
        {
            "ok": ok, "error": error,
            "user": user, "item": item,
            "categories": categories, "locations": locations,
            "custom_fields_by_category": custom_fields_by_category,
            "custom_field_values": custom_field_values,
        },
    )


@router.post("/{item_id}/edit")
async def update_item(
    request: Request,
    item_id: uuid.UUID,
    barcode: str = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    location: str = Form(""),
    notes: str = Form(""),
    status: str = Form(...),
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, item.department_id):
        raise Forbidden()

    result = await session.exec(
        select(Item).where(Item.barcode == barcode, Item.id != item_id, Item.deleted_at.is_(None))
    )
    if result.first() or await barcode_taken_by_other_kind(session, barcode, kind="item"):
        categories, locations = await presets(session, item.department_id)
        custom_fields_by_category = await get_definitions_by_category(session, item.department_id)
        custom_field_values = await get_values_for_item(session, item.id)
        return templates.TemplateResponse(
            request,
            "items/form.html",
            {
                "user": user, "item": item,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "categories": categories, "locations": locations,
                "custom_fields_by_category": custom_fields_by_category,
                "custom_field_values": custom_field_values,
            },
            status_code=409,
        )

    # Lending bleibt die alleinige Quelle der Wahrheit für "ausgeliehen"
    # (siehe app/models/lending.py) - eine offene Lending darf nicht durch
    # eine Statusänderung im Formular stillschweigend übergangen werden,
    # sonst bliebe sie offen und über den normalen Scan-Rückgabe-Weg nicht
    # mehr erreichbar (das Formular selbst bietet "ausgeliehen" nur an, wenn
    # der Gegenstand das aktuell schon ist - dieser Fall wird also nur bei
    # manipulierten Formulardaten oder einer parallel begonnenen Ausleihe
    # überhaupt erreicht).
    new_status = ItemStatus(status)
    if new_status != ItemStatus.AUSGELIEHEN:
        open_lending = await session.exec(
            select(Lending).where(Lending.item_id == item.id, Lending.returned_at.is_(None))
        )
        if open_lending.first():
            categories, locations = await presets(session, item.department_id)
            custom_fields_by_category = await get_definitions_by_category(session, item.department_id)
            custom_field_values = await get_values_for_item(session, item.id)
            return templates.TemplateResponse(
                request,
                "items/form.html",
                {
                    "user": user, "item": item,
                    "error": "Gegenstand hat noch eine offene Ausleihe - erst über Scannen zurückgeben, dann Status ändern.",
                    "categories": categories, "locations": locations,
                    "custom_fields_by_category": custom_fields_by_category,
                    "custom_field_values": custom_field_values,
                },
                status_code=409,
            )

    item.barcode = barcode
    item.name = name
    item.category = category or None
    item.location = location or None
    item.notes = notes or None
    item.status = new_status

    form_data = await request.form()
    custom_field_errors = await save_values_for_item(session, item, form_data)
    if custom_field_errors:
        categories, locations = await presets(session, item.department_id)
        custom_fields_by_category = await get_definitions_by_category(session, item.department_id)
        custom_field_values = await get_values_for_item(session, item.id)
        return templates.TemplateResponse(
            request,
            "items/form.html",
            {
                "user": user, "item": item,
                "error": " ".join(custom_field_errors),
                "categories": categories, "locations": locations,
                "custom_fields_by_category": custom_fields_by_category,
                "custom_field_values": custom_field_values,
            },
            status_code=400,
        )

    session.add(item)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        logger.warning("Aktualisieren von Gegenstand %s kollidierte mit einer gleichzeitigen Änderung (Barcode '%s').", item_id, barcode)
        return RedirectResponse(url="/items?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/items", status_code=303)


@router.post("/{item_id}/delete")
async def delete_item(
    item_id: uuid.UUID,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    return await delete_entity(session, ITEM_KIND, item_id, user)


@router.post("/{item_id}/image")
async def upload_item_image(
    item_id: uuid.UUID,
    image: UploadFile,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    return await upload_entity_image(session, ITEM_KIND, item_id, image, user)


@router.post("/{item_id}/image/delete")
async def delete_item_image(
    item_id: uuid.UUID,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    return await delete_entity_image(session, ITEM_KIND, item_id, user)
