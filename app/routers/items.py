"""
CRUD für Gegenstände (Items). Abteilungsgescoped: Mitarbeiter sehen/bearbeiten
nur ihre eigene Abteilung, Admins können zwischen Abteilungen wechseln oder
alle sehen (Anlegen/Bearbeiten erfordert dann aber eine gewählte Abteilung).
"""
import uuid


from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import Forbidden, get_current_department, get_current_user
from app.core.templating import templates
from app.core.uploads import InvalidImage, delete_image, has_image, image_url, save_image
from app.models.common import ItemStatus, utcnow
from app.models.department import Department
from app.models.item import Item
from app.models.preset import Category, Location
from app.models.user import User

router = APIRouter(prefix="/items", tags=["items"])


async def _presets(session: AsyncSession, department_id):
    categories = (await session.exec(
        select(Category).where(Category.department_id == department_id).order_by(Category.name)
    )).all()
    locations = (await session.exec(
        select(Location).where(Location.department_id == department_id).order_by(Location.name)
    )).all()
    return categories, locations


@router.get("")
async def list_items(
    request: Request,
    q: str = "",
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    stmt = select(Item).where(Item.deleted_at.is_(None)).order_by(Item.name)
    if department:
        stmt = stmt.where(Item.department_id == department.id)
    if q:
        like = f"%{q}%"
        stmt = stmt.where((Item.name.ilike(like)) | (Item.barcode.ilike(like)))

    result = await session.exec(stmt)
    items = result.all()

    # Offene Reservierungen der angezeigten Items (für "Reserviert"-Chip + Button-Logik)
    from app.models.reservation import Reservation
    from app.routers.reservations import get_linked_worker
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

    linked_worker = await get_linked_worker(session, user)

    return templates.TemplateResponse(
        request,
        "items/list.html",
        {
            "user": user, "department": department, "items": items, "q": q, "ok": ok, "error": error,
            "reserved_ids": reserved_ids, "linked_worker": linked_worker,
        },
    )


@router.get("/new")
async def new_item_form(
    request: Request,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    if not department:
        raise Forbidden()  # Admin ohne gewählte Abteilung kann nichts anlegen - Zielabteilung ist nicht eindeutig
    categories, locations = await _presets(session, department.id)
    return templates.TemplateResponse(
        request,
        "items/form.html",
        {
            "user": user, "department": department, "item": None, "error": None,
            "categories": categories, "locations": locations,
        },
    )


@router.post("/new")
async def create_item(
    request: Request,
    barcode: str = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    location: str = Form(""),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    if not department:
        raise Forbidden()

    result = await session.exec(select(Item).where(Item.barcode == barcode, Item.deleted_at.is_(None)))
    if result.first():
        categories, locations = await _presets(session, department.id)
        return templates.TemplateResponse(
            request,
            "items/form.html",
            {
                "user": user, "department": department, "item": None,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "categories": categories, "locations": locations,
            },
            status_code=409,
        )

    item = Item(
        barcode=barcode, name=name,
        category=category or None, location=location or None, notes=notes or None,
        department_id=department.id,
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
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None or (department and item.department_id != department.id):
        raise Forbidden()

    categories, locations = await _presets(session, item.department_id)
    return templates.TemplateResponse(
        request,
        "items/form.html",
        {
            "ok": ok, "error": error,
            "user": user, "department": department, "item": item, "error": None,
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
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None or (department and item.department_id != department.id):
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
                "user": user, "department": department, "item": item,
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
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None or (department and item.department_id != department.id):
        raise Forbidden()

    item.deleted_at = utcnow()
    session.add(item)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return RedirectResponse(url="/items?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/items", status_code=303)


@router.post("/{item_id}/image")
async def upload_item_image(
    item_id: uuid.UUID,
    image: UploadFile,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None or (department and item.department_id != department.id):
        raise Forbidden()

    try:
        await save_image(image, "items", item.id)
    except InvalidImage as exc:
        return RedirectResponse(url=f"/items/{item_id}/edit?error={exc}", status_code=303)

    return RedirectResponse(url=f"/items/{item_id}/edit?ok=Bild+aktualisiert.", status_code=303)


@router.post("/{item_id}/image/delete")
async def delete_item_image(
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None or (department and item.department_id != department.id):
        raise Forbidden()

    delete_image("items", item.id)
    return RedirectResponse(url=f"/items/{item_id}/edit?ok=Bild+entfernt.", status_code=303)
