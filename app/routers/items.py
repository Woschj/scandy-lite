"""
CRUD für Gegenstände (Items). Abteilungsgescoped über UserDepartmentRole:
Sichtbarkeit richtet sich danach, in welchen Abteilungen ein User überhaupt
eine Rolle hat; Verwalten (Anlegen/Bearbeiten/Löschen) erfordert zusätzlich
die Mitarbeiter-Rolle SPEZIFISCH in der jeweiligen Abteilung.

Kein "aktuell aktive Abteilung"-Kontext (kein Umschalter) - die Liste zeigt
immer alles Sichtbare gemischt (mit Abteilungs-Badge pro Karte), und beim
Anlegen ist die Abteilung ein normales Formularfeld.
"""
import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_accessible_departments, get_department_roles, get_visible_department_ids, is_staff_in_department
from app.core.database import get_session
from app.core.deps import Forbidden, get_current_user, populate_nav_context, require_staff, verify_csrf
from app.core.responses import redirect_with_query
from app.core.templating import templates
from app.core.uploads import InvalidImage, delete_image, has_image, image_url, save_image
from app.models.common import ItemStatus, UserRole, utcnow
from app.models.item import Item
from app.models.preset import Category, Location
from app.models.user import User

router = APIRouter(prefix="/items", tags=["items"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


async def _presets(session: AsyncSession, department_id):
    categories = (await session.exec(
        select(Category).where(Category.department_id == department_id).order_by(Category.name)
    )).all()
    locations = (await session.exec(
        select(Location).where(Location.department_id == department_id).order_by(Location.name)
    )).all()
    return categories, locations


async def _staff_departments(session: AsyncSession, user: User):
    """Abteilungen, in denen dieser User anlegen/bearbeiten darf - für das
    Abteilungs-Auswahlfeld im Anlegen-Formular."""
    if user.is_admin:
        return await get_accessible_departments(session, user)
    roles = await get_department_roles(session, user)
    dept_ids = {r.department_id for r in roles if r.role == UserRole.MITARBEITER}
    if not dept_ids:
        return []
    all_accessible = await get_accessible_departments(session, user)
    return [d for d in all_accessible if d.id in dept_ids]


@router.get("")
async def list_items(
    request: Request,
    q: str = "",
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from app.models.reservation import Reservation
    from app.routers.reservations import get_linked_worker

    linked_worker = await get_linked_worker(session, user)

    stmt = select(Item).where(Item.deleted_at.is_(None)).order_by(Item.name).options(selectinload(Item.department))

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

    result = await session.exec(stmt)
    items = result.all()

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
            "reserved_ids": reserved_ids, "linked_worker": linked_worker,
            "staff_department_ids": staff_department_ids,
        },
    )


@router.get("/new")
async def new_item_form(
    request: Request,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    departments = await _staff_departments(session, user)
    if not departments:
        raise Forbidden()  # keine Abteilung, in der dieser User Mitarbeiter-Rolle hat

    return templates.TemplateResponse(
        request,
        "items/form.html",
        {
            "user": user, "item": None, "error": None,
            "departments": departments, "categories": [], "locations": [],
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
    if result.first():
        departments = await _staff_departments(session, user)
        categories, locations = await _presets(session, department_id)
        return templates.TemplateResponse(
            request,
            "items/form.html",
            {
                "user": user, "item": None,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "departments": departments, "categories": categories, "locations": locations,
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
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return RedirectResponse(url="/items?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/items", status_code=303)


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

    categories, locations = await _presets(session, item.department_id)
    return templates.TemplateResponse(
        request,
        "items/form.html",
        {
            "ok": ok, "error": error,
            "user": user, "item": item,
            "categories": categories, "locations": locations,
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
    if result.first():
        categories, locations = await _presets(session, item.department_id)
        return templates.TemplateResponse(
            request,
            "items/form.html",
            {
                "user": user, "item": item,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "categories": categories, "locations": locations,
            },
            status_code=409,
        )

    item.barcode = barcode
    item.name = name
    item.category = category or None
    item.location = location or None
    item.notes = notes or None
    item.status = ItemStatus(status)
    session.add(item)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return RedirectResponse(url="/items?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/items", status_code=303)


@router.post("/{item_id}/delete")
async def delete_item(
    item_id: uuid.UUID,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, item.department_id):
        raise Forbidden()

    item.deleted_at = utcnow()
    session.add(item)
    await session.commit()
    return RedirectResponse(url="/items", status_code=303)


@router.post("/{item_id}/image")
async def upload_item_image(
    item_id: uuid.UUID,
    image: UploadFile,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, item.department_id):
        raise Forbidden()

    try:
        await save_image(image, "items", item.id)
    except InvalidImage as exc:
        return redirect_with_query(f"/items/{item_id}/edit", error=str(exc))

    return RedirectResponse(url=f"/items/{item_id}/edit?ok=Bild+aktualisiert.", status_code=303)


@router.post("/{item_id}/image/delete")
async def delete_item_image(
    item_id: uuid.UUID,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, item.department_id):
        raise Forbidden()

    delete_image("items", item.id)
    return RedirectResponse(url=f"/items/{item_id}/edit?ok=Bild+entfernt.", status_code=303)
