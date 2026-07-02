"""
CRUD für Gegenstände (Items). Abteilungsgescoped: Mitarbeiter sehen/bearbeiten
nur ihre eigene Abteilung, Admins können zwischen Abteilungen wechseln oder
alle sehen (Anlegen/Bearbeiten erfordert dann aber eine gewählte Abteilung).
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import Forbidden, get_current_department, get_current_user
from app.core.templating import templates
from app.models.common import ItemStatus
from app.models.department import Department
from app.models.item import Item
from app.models.user import User

router = APIRouter(prefix="/items", tags=["items"])


@router.get("")
async def list_items(
    request: Request,
    q: str = "",
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

    return templates.TemplateResponse(
        request,
        "items/list.html",
        {"user": user, "department": department, "items": items, "q": q},
    )


@router.get("/new")
async def new_item_form(
    request: Request,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
):
    if not department:
        raise Forbidden()  # Admin ohne gewählte Abteilung kann nichts anlegen - Zielabteilung ist nicht eindeutig
    return templates.TemplateResponse(
        request,
        "items/form.html",
        {"user": user, "department": department, "item": None, "error": None},
    )


@router.post("/new")
async def create_item(
    request: Request,
    barcode: str = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    location: str = Form(""),
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    if not department:
        raise Forbidden()

    result = await session.exec(select(Item).where(Item.barcode == barcode, Item.deleted_at.is_(None)))
    if result.first():
        return templates.TemplateResponse(
            request,
            "items/form.html",
            {
                "user": user, "department": department, "item": None,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
            },
            status_code=409,
        )

    item = Item(
        barcode=barcode, name=name,
        category=category or None, location=location or None,
        department_id=department.id,
    )
    session.add(item)
    await session.commit()
    return RedirectResponse(url="/items", status_code=303)


@router.get("/{item_id}/edit")
async def edit_item_form(
    request: Request,
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    item = await session.get(Item, item_id)
    if not item or item.deleted_at is not None or (department and item.department_id != department.id):
        raise Forbidden()

    return templates.TemplateResponse(
        request,
        "items/form.html",
        {"user": user, "department": department, "item": item, "error": None},
    )


@router.post("/{item_id}/edit")
async def update_item(
    request: Request,
    item_id: uuid.UUID,
    barcode: str = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    location: str = Form(""),
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
        return templates.TemplateResponse(
            request,
            "items/form.html",
            {
                "user": user, "department": department, "item": item,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
            },
            status_code=409,
        )

    item.barcode = barcode
    item.name = name
    item.category = category or None
    item.location = location or None
    item.status = ItemStatus(status)
    session.add(item)
    await session.commit()
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

    item.deleted_at = datetime.now(timezone.utc)
    session.add(item)
    await session.commit()
    return RedirectResponse(url="/items", status_code=303)
