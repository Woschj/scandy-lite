"""
Gemeinsame Barcode-Eindeutigkeitsprüfung ÜBER Item und Consumable hinweg.

Jede der beiden Tabellen erzwingt Eindeutigkeit bisher nur für sich selbst
(partieller Unique-Index je Tabelle, siehe Migration 45dd75eab85a) - ohne
diesen Cross-Check könnten ein Gegenstand und ein Verbrauchsmaterial
denselben Barcode bekommen. app.routers.scan.scan_lookup prüft beim Scannen
Item ZUERST und würde einen gleichlautenden Consumable-Barcode danach
dauerhaft maskieren (nie mehr über Scannen erreichbar, nur noch per Liste/
Direktlink).
"""
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.consumable import Consumable
from app.models.item import Item


async def barcode_taken_by_other_kind(session: AsyncSession, barcode: str, *, kind: str) -> bool:
    """kind = 'item' oder 'consumable' - die eigene Tabelle wird an der
    jeweiligen Aufrufstelle bereits separat geprüft, hier wird nur die
    JEWEILS ANDERE zusätzlich abgedeckt."""
    if kind == "item":
        result = await session.exec(select(Consumable).where(Consumable.barcode == barcode, Consumable.deleted_at.is_(None)))
    else:
        result = await session.exec(select(Item).where(Item.barcode == barcode, Item.deleted_at.is_(None)))
    return result.first() is not None
