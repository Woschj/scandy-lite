"""
Gemeinsame Bausteine für Items UND Consumables: beide werden identisch
Kategorie-/Standort-gescoped präsentiert (_presets*, _staff_departments) und
identisch weich gelöscht/mit Bild versehen (delete_entity, upload_entity_image,
delete_entity_image) - nur Modell und URL-Prefix unterscheiden sich. Dieses
Modul hält diese Logik an EINER Stelle statt sie in app/routers/items.py und
app/routers/consumables.py dupliziert zu pflegen.

Alles, was fachlich zwischen Item und Consumable abweicht (Formularfelder,
Bestandsführung, Barcode-Konfliktbehandlung beim Anlegen/Bearbeiten), bleibt
bewusst in den jeweiligen Routern - hier steht nur, was wortgleich ist.
"""
from dataclasses import dataclass
from typing import Type

from fastapi import UploadFile
from fastapi.responses import RedirectResponse
from sqlmodel import SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.access import get_accessible_departments, get_department_roles, is_staff_in_department
from app.core.deps import Forbidden
from app.core.responses import redirect_with_query
from app.core.uploads import InvalidImage, delete_image, save_image
from app.models.common import UserRole, utcnow
from app.models.preset import Category, Location
from app.models.user import User


async def presets(session: AsyncSession, department_id) -> tuple[list, list]:
    categories = (await session.exec(
        select(Category).where(Category.department_id == department_id).order_by(Category.name)
    )).all()
    locations = (await session.exec(
        select(Location).where(Location.department_id == department_id).order_by(Location.name)
    )).all()
    return categories, locations


async def presets_by_department(session: AsyncSession, department_ids: list) -> tuple[dict, dict]:
    """Kategorie-/Standort-Vorschläge ALLER übergebenen Abteilungen, gruppiert
    nach (als String) Abteilungs-ID - fürs Anlegen-Formular, wo die Abteilung
    erst im Formular selbst gewählt wird (Alpine blendet dann die passende
    Gruppe ein, siehe items/form.html bzw. consumables/form.html - gleiches
    Prinzip wie bei den Zusatzfeldern pro Kategorie)."""
    if not department_ids:
        return {}, {}
    categories = (await session.exec(
        select(Category).where(Category.department_id.in_(department_ids)).order_by(Category.name)
    )).all()
    locations = (await session.exec(
        select(Location).where(Location.department_id.in_(department_ids)).order_by(Location.name)
    )).all()
    categories_by_department: dict = {}
    for c in categories:
        categories_by_department.setdefault(str(c.department_id), []).append(c.name)
    locations_by_department: dict = {}
    for l in locations:
        locations_by_department.setdefault(str(l.department_id), []).append(l.name)
    return categories_by_department, locations_by_department


async def staff_departments(session: AsyncSession, user: User):
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


@dataclass(frozen=True)
class InventoryKind:
    model: Type[SQLModel]
    url_prefix: str  # "items" | "consumables" - sowohl Routen-Präfix als auch Upload-Unterverzeichnis


async def _load_owned_entity(session: AsyncSession, kind: InventoryKind, entity_id, user: User):
    entity = await session.get(kind.model, entity_id)
    if not entity or entity.deleted_at is not None:
        raise Forbidden()
    if not await is_staff_in_department(session, user, entity.department_id):
        raise Forbidden()
    return entity


async def delete_entity(session: AsyncSession, kind: InventoryKind, entity_id, user: User) -> RedirectResponse:
    entity = await _load_owned_entity(session, kind, entity_id, user)
    entity.deleted_at = utcnow()
    session.add(entity)
    await session.commit()
    return RedirectResponse(url=f"/{kind.url_prefix}", status_code=303)


async def upload_entity_image(session: AsyncSession, kind: InventoryKind, entity_id, image: UploadFile, user: User):
    entity = await _load_owned_entity(session, kind, entity_id, user)
    try:
        await save_image(image, kind.url_prefix, entity.id)
    except InvalidImage as exc:
        return redirect_with_query(f"/{kind.url_prefix}/{entity_id}/edit", error=str(exc))
    return RedirectResponse(url=f"/{kind.url_prefix}/{entity_id}/edit?ok=Bild+aktualisiert.", status_code=303)


async def delete_entity_image(session: AsyncSession, kind: InventoryKind, entity_id, user: User) -> RedirectResponse:
    entity = await _load_owned_entity(session, kind, entity_id, user)
    delete_image(kind.url_prefix, entity.id)
    return RedirectResponse(url=f"/{kind.url_prefix}/{entity_id}/edit?ok=Bild+entfernt.", status_code=303)
