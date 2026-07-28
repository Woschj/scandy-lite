"""
Kategorien-/Standort-Vorschläge und Zusatzfelder (pro Kategorie, nur
Gegenstände) - die Stammdaten-Presets, die die Item-/Consumable-Formulare
befüllen.
"""
import uuid

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import populate_nav_context, require_admin, verify_csrf
from app.core.responses import redirect_with_query
from app.models.common import CustomFieldType
from app.models.custom_field import CustomFieldDefinition, CustomFieldValue
from app.models.preset import Category, Location
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


# --- Kategorien --------------------------------------------------------

@router.post("/categories/new")
async def create_category(
    name: str = Form(...),
    department_id: uuid.UUID = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(
        select(Category).where(Category.department_id == department_id, Category.name == name)
    )
    if not result.first():
        session.add(Category(name=name.strip(), department_id=department_id))
        await session.commit()
    return RedirectResponse(url="/admin/settings#categories", status_code=303)


@router.post("/categories/{category_id}/delete")
async def delete_category(
    category_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    category = await session.get(Category, category_id)
    if not category:
        return RedirectResponse(url="/admin/settings#categories", status_code=303)

    # Zusatzfelder hängen per Fremdschlüssel an der Kategorie (siehe
    # app/models/custom_field.py) - ohne diese Prüfung würde das Löschen
    # entweder an der FK-Constraint scheitern (Postgres) oder verwaiste
    # Referenzen hinterlassen. Gleiches Blocker-Muster wie delete_department
    # in admin_departments.py, inklusive konkreter Feldnamen statt nur einer
    # Anzahl.
    fields_result = await session.exec(
        select(CustomFieldDefinition).where(CustomFieldDefinition.category_id == category_id).limit(4)
    )
    fields = fields_result.all()
    if fields:
        names = ", ".join(f.name for f in fields[:3])
        if len(fields) > 3:
            field_count = (
                await session.exec(
                    select(func.count()).select_from(CustomFieldDefinition).where(CustomFieldDefinition.category_id == category_id)
                )
            ).one()
            names += f", … ({field_count} gesamt)"
        message = (
            f"'{category.name}' kann nicht gelöscht werden, hat noch Zusatzfelder: {names}. "
            "Erst im Tab 'Zusatzfelder' entfernen."
        )
        return redirect_with_query("/admin/settings", fragment="categories", error=message)

    await session.delete(category)
    await session.commit()
    return RedirectResponse(url="/admin/settings#categories", status_code=303)


# --- Zusatzfelder (pro Kategorie, nur Gegenstände) ----------------------

@router.post("/custom-fields/new")
async def create_custom_field(
    category_id: uuid.UUID = Form(...),
    name: str = Form(...),
    field_type: str = Form(...),
    options: str = Form(""),
    visible_to_all: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    try:
        parsed_type = CustomFieldType(field_type)
    except ValueError:
        return redirect_with_query("/admin/settings", fragment="custom-fields", error="Ungültiger Feldtyp.")

    session.add(
        CustomFieldDefinition(
            category_id=category_id,
            name=name.strip(),
            field_type=parsed_type,
            options=options.strip() or None,
            visible_to_all=bool(visible_to_all),
        )
    )
    await session.commit()
    return redirect_with_query("/admin/settings", fragment="custom-fields", ok="Zusatzfeld angelegt.")


@router.post("/custom-fields/{field_id}/delete")
async def delete_custom_field(
    field_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    field = await session.get(CustomFieldDefinition, field_id)
    if field:
        # Zugehörige Werte an Gegenständen gehören zu diesem Feld - werden
        # mitgelöscht statt verwaist zu bleiben (kein eigenständiger Sinn
        # ohne die Definition, die Typ/Optionen vorgibt).
        values_result = await session.exec(select(CustomFieldValue).where(CustomFieldValue.field_id == field_id))
        for value in values_result.all():
            await session.delete(value)
        await session.delete(field)
        await session.commit()
    return redirect_with_query("/admin/settings", fragment="custom-fields", ok="Zusatzfeld entfernt.")


# --- Standorte ---------------------------------------------------------

@router.post("/locations/new")
async def create_location(
    name: str = Form(...),
    department_id: uuid.UUID = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(
        select(Location).where(Location.department_id == department_id, Location.name == name)
    )
    if not result.first():
        session.add(Location(name=name.strip(), department_id=department_id))
        await session.commit()
    return RedirectResponse(url="/admin/settings#locations", status_code=303)


@router.post("/locations/{location_id}/delete")
async def delete_location(
    location_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    location = await session.get(Location, location_id)
    if location:
        await session.delete(location)
        await session.commit()
    return RedirectResponse(url="/admin/settings#locations", status_code=303)
