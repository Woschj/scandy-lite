"""
Papierkorb (soft-gelöschte Gegenstände/Material/Mitarbeiter) - Wieder-
herstellen oder endgültig löschen.

restore_trashed_*/purge_trashed_* unterscheiden sich zwischen Item/
Consumable/User nur in Modell, Anzeigename und der zugrunde liegenden
restore_*/purge_*-Funktion aus app.core.trash - _TrashKind bündelt das,
die Routen selbst bleiben dünne, URL-adressierbare Wrapper.
"""
import uuid
from dataclasses import dataclass
from typing import Callable

from fastapi import APIRouter, Depends, Form
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import populate_nav_context, require_admin, verify_csrf
from app.core.responses import redirect_with_query
from app.core.trash import (
    purge_consumable,
    purge_item,
    purge_user,
    restore_consumable,
    restore_item,
    restore_user,
)
from app.models.consumable import Consumable
from app.models.item import Item
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


@dataclass(frozen=True)
class _TrashKind:
    model: type
    not_found_label: str
    restore_fn: Callable
    purge_fn: Callable
    name_fn: Callable[[object], str]


_TRASH_KINDS = {
    "items": _TrashKind(Item, "Gegenstand", restore_item, purge_item, lambda e: e.name),
    "consumables": _TrashKind(Consumable, "Verbrauchsmaterial", restore_consumable, purge_consumable, lambda e: e.name),
    "users": _TrashKind(User, "Benutzer", restore_user, purge_user, lambda e: e.full_name),
}


async def _restore_trashed(session: AsyncSession, kind_key: str, entity_id: uuid.UUID):
    kind = _TRASH_KINDS[kind_key]
    entity = await session.get(kind.model, entity_id)
    if not entity or entity.deleted_at is None:
        return redirect_with_query("/admin/settings", fragment="trash", error=f"{kind.not_found_label} nicht gefunden.")
    error = await kind.restore_fn(session, entity)
    if error:
        return redirect_with_query("/admin/settings", fragment="trash", error=error)
    await session.commit()
    return redirect_with_query("/admin/settings", fragment="trash", ok=f"{kind.name_fn(entity)} wiederhergestellt.")


async def _purge_trashed(session: AsyncSession, kind_key: str, entity_id: uuid.UUID, force: str):
    kind = _TRASH_KINDS[kind_key]
    entity = await session.get(kind.model, entity_id)
    if not entity or entity.deleted_at is None:
        return redirect_with_query("/admin/settings", fragment="trash", error=f"{kind.not_found_label} nicht gefunden.")
    name = kind.name_fn(entity)
    error = await kind.purge_fn(session, entity, force=bool(force))
    if error:
        return redirect_with_query("/admin/settings", fragment="trash", error=error)
    await session.commit()
    return redirect_with_query("/admin/settings", fragment="trash", ok=f"{name} endgültig gelöscht.")


@router.post("/trash/items/{item_id}/restore")
async def restore_trashed_item(
    item_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _restore_trashed(session, "items", item_id)


@router.post("/trash/items/{item_id}/purge")
async def purge_trashed_item(
    item_id: uuid.UUID,
    force: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _purge_trashed(session, "items", item_id, force)


@router.post("/trash/consumables/{consumable_id}/restore")
async def restore_trashed_consumable(
    consumable_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _restore_trashed(session, "consumables", consumable_id)


@router.post("/trash/consumables/{consumable_id}/purge")
async def purge_trashed_consumable(
    consumable_id: uuid.UUID,
    force: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _purge_trashed(session, "consumables", consumable_id, force)


@router.post("/trash/users/{trashed_user_id}/restore")
async def restore_trashed_user(
    trashed_user_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _restore_trashed(session, "users", trashed_user_id)


@router.post("/trash/users/{trashed_user_id}/purge")
async def purge_trashed_user(
    trashed_user_id: uuid.UUID,
    force: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    return await _purge_trashed(session, "users", trashed_user_id, force)
