"""
CRUD für Verbrauchsmaterial + Bestandsanpassung. Eine Entnahme mit gewähltem
Mitarbeiter wird als ConsumableUsage protokolliert (Grundlage der Historie);
reiner Nachschub (kein Mitarbeiter gewählt) verändert nur den Bestand.

Abteilungsgescoped über UserDepartmentRole - siehe items.py für die
ausführliche Erklärung des Berechtigungsmodells, hier identisch angewendet.
"""
import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import is_staff_in_department, get_visible_department_ids, get_department_roles
from app.core.database import get_session
from app.core.deps import Forbidden, get_current_department, get_current_user, require_staff, populate_switchable_departments
from app.core.templating import templates
from app.core.uploads import InvalidImage, delete_image, has_image, image_url, save_image
from app.models.common import utcnow
from app.models.consumable import Consumable, ConsumableUsage
from app.models.department import Department
from app.models.preset import Category, Location
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(prefix="/consumables", tags=["consumables"], dependencies=[Depends(populate_switchable_departments)])


async def _presets(session: AsyncSession, department_id):
    categories = (await session.exec(
        select(Category).where(Category.department_id == department_id).order_by(Category.name)
    )).all()
    locations = (await session.exec(
        select(Location).where(Location.department_id == department_id).order_by(Location.name)
    )).all()
    return categories, locations


@router.get("")
async def list_consumables(
    request: Request,
    q: str = "",
    ok: str = "",
    error: str = "",
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    from app.routers.reservations import get_linked_worker

    linked_worker = await get_linked_worker(session, user)

    stmt = select(Consumable).where(Consumable.deleted_at.is_(None)).order_by(Consumable.name)
    show_department_badge = False
    is_staff_here = False
    staff_department_ids: set = set()

    if not user.is_admin:
        roles = await get_department_roles(session, user)
        staff_department_ids = {r.department_id for r in roles if r.role.value == "mitarbeiter"}

    if department:
        stmt = stmt.where(Consumable.department_id == department.id)
        is_staff_here = await is_staff_in_department(session, user, department.id)
    else:
        visible_ids = await get_visible_department_ids(session, user)
        if visible_ids is not None:
            stmt = stmt.where(Consumable.department_id.in_(visible_ids))
        show_department_badge = True

    if q:
        like = f"%{q}%"
        stmt = stmt.where((Consumable.name.ilike(like)) | (Consumable.barcode.ilike(like)))

    if show_department_badge:
        stmt = stmt.options(selectinload(Consumable.department))

    result = await session.exec(stmt)
    consumables = result.all()

    return templates.TemplateResponse(
        request,
        "consumables/list.html",
        {
            "user": user, "department": department, "consumables": consumables, "q": q, "ok": ok, "error": error,
            "show_department_badge": show_department_badge, "linked_worker": linked_worker,
            "is_staff_here": is_staff_here, "staff_department_ids": staff_department_ids,
        },
    )


@router.get("/new")
async def new_consumable_form(
    request: Request,
    user: User = Depends(require_staff),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    if not department:
        raise Forbidden()
    if not await is_staff_in_department(session, user, department.id):
        raise Forbidden()

    categories, locations = await _presets(session, department.id)
    return templates.TemplateResponse(
        request,
        "consumables/form.html",
        {
            "user": user, "department": department, "consumable": None, "error": None,
            "categories": categories, "locations": locations,
        },
    )


@router.post("/new")
async def create_consumable(
    request: Request,
    barcode: str = Form(...),
    name: str = Form(...),
    category: str = Form(""),
    location: str = Form(""),
    unit: str = Form("Stück"),
    quantity: int = Form(0),
    min_quantity: int = Form(0),
    user: User = Depends(require_staff),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    if not department:
        raise Forbidden()
    if not await is_staff_in_department(session, user, department.id):
        raise Forbidden()

    result = await session.exec(
        select(Consumable).where(Consumable.barcode == barcode, Consumable.deleted_at.is_(None))
    )
    if result.first():
        categories, locations = await _presets(session, department.id)
        return templates.TemplateResponse(
            request,
            "consumables/form.html",
            {
                "user": user, "department": department, "consumable": None,
                "error": f"Barcode '{barcode}' ist bereits vergeben.",
                "categories": categories, "locations": locations,
            },
            status_code=409,
        )

    consumable = Consumable(
        barcode=barcode, name=name, category=category or None, location=location or None,
        unit=unit or "Stück", quantity=max(quantity, 0), min_quantity=max(min_quantity, 0),
        department_id=department.id,
    )
    session.add(consumable)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return RedirectResponse(url="/consumables?error=Barcode+ist+bereits+vergeben.", status_code=303)
    return RedirectResponse(url="/consumables", status_code=303)


@router.get("/{consumable_id}/edit")
async def edit_consumable_form(
    request: Request,
    consumable_id: uuid.UUID,
    ok: str = "",
    error: str = "",
    user: User = Depends(require_staff),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    consumable = await session.get(Consumable, consumable_id)
    if not consumable or consumable.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, consumable.department_id):
        raise Forbidden()

    workers_result = await session.exec(
        select(Worker).where(Worker.department_id == consumable.department_id, Worker.deleted_at.is_(None)).order_by(Worker.last_name)
    )
    categories, locations = await _presets(session, consumable.department_id)
    return templates.TemplateResponse(
        request,
        "consumables/form.html",
        {
            "user": user, "department": department, "consumable": consumable, "error": error, "ok": ok,
            "workers": workers_result.all(),
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
    department: Department | None = Depends(get_current_department),
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
    if result.first():
        categories, locations = await _presets(session, consumable.department_id)
        return templates.TemplateResponse(
            request,
            "consumables/form.html",
            {
                "user": user, "department": department, "consumable": consumable,
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

    new_quantity = consumable.quantity + delta
    if new_quantity < 0:
        raise Forbidden()  # kein negativer Bestand - kein stiller Fehlerfall, sondern harter Stop

    consumable.quantity = new_quantity
    session.add(consumable)

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
    consumable = await session.get(Consumable, consumable_id)
    if not consumable or consumable.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, consumable.department_id):
        raise Forbidden()

    consumable.deleted_at = utcnow()
    session.add(consumable)
    await session.commit()
    return RedirectResponse(url="/consumables", status_code=303)


@router.post("/{consumable_id}/image")
async def upload_consumable_image(
    consumable_id: uuid.UUID,
    image: UploadFile,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    consumable = await session.get(Consumable, consumable_id)
    if not consumable or consumable.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, consumable.department_id):
        raise Forbidden()

    try:
        await save_image(image, "consumables", consumable.id)
    except InvalidImage as exc:
        return RedirectResponse(url=f"/consumables/{consumable_id}/edit?error={exc}", status_code=303)

    return RedirectResponse(url=f"/consumables/{consumable_id}/edit?ok=Bild+aktualisiert.", status_code=303)


@router.post("/{consumable_id}/image/delete")
async def delete_consumable_image(
    consumable_id: uuid.UUID,
    user: User = Depends(require_staff),
    session: AsyncSession = Depends(get_session),
):
    consumable = await session.get(Consumable, consumable_id)
    if not consumable or consumable.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, consumable.department_id):
        raise Forbidden()

    delete_image("consumables", consumable.id)
    return RedirectResponse(url=f"/consumables/{consumable_id}/edit?ok=Bild+entfernt.", status_code=303)
