"""
Historie - kombinierte, chronologische Zeitleiste aus Ausleihen, Rückgaben und
Verbrauchsmaterial-Entnahmen. Bewusst als EINE Ansicht statt getrennter
Tool-Historie/Worker-Historie/Consumable-Historie (wie im Original) - für ein
schlankes System reicht eine gemeinsame, filterbare Liste.
"""
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.access import get_visible_department_ids
from app.core.deps import get_current_user, populate_nav_context, require_staff
from app.core.templating import templates
from app.models.consumable import Consumable, ConsumableUsage
from app.models.item import Item
from app.models.lending import Lending
from app.models.user import User

router = APIRouter(prefix="/history", tags=["history"], dependencies=[Depends(populate_nav_context), Depends(require_staff)])

_FETCH_LIMIT = 300  # pro Quelle - für ein internes Tool ausreichend, keine Pagination-API nötig
_PAGE_SIZE = 50


@dataclass
class HistoryEntry:
    timestamp: datetime
    action: str  # "ausgeliehen" | "zurückgegeben" | "entnommen"
    title: str
    subtitle: str  # Mitarbeitername
    detail: str = ""


@router.get("")
async def history_index(
    request: Request,
    q: str = "",
    page: int = 1,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    entries: list[HistoryEntry] = []
    visible_ids = await get_visible_department_ids(session, user)  # None = Admin (alles)

    lending_stmt = (
        select(Lending)
        .options(selectinload(Lending.item), selectinload(Lending.worker))
        .order_by(Lending.lent_at.desc())
        .limit(_FETCH_LIMIT)
    )
    if visible_ids is not None:
        lending_stmt = lending_stmt.where(Lending.department_id.in_(visible_ids))
    lendings = (await session.exec(lending_stmt)).all()

    for lending in lendings:
        item_name = lending.item.name if lending.item else "(gelöschter Gegenstand)"
        worker_name = lending.worker.full_name if lending.worker else "(gelöschter Mitarbeiter)"
        entries.append(HistoryEntry(
            timestamp=lending.lent_at, action="ausgeliehen", title=item_name, subtitle=worker_name,
        ))
        if lending.returned_at:
            entries.append(HistoryEntry(
                timestamp=lending.returned_at, action="zurückgegeben", title=item_name, subtitle=worker_name,
            ))

    usage_stmt = (
        select(ConsumableUsage)
        .join(Consumable)
        .options(selectinload(ConsumableUsage.consumable), selectinload(ConsumableUsage.worker))
        .order_by(ConsumableUsage.used_at.desc())
        .limit(_FETCH_LIMIT)
    )
    if visible_ids is not None:
        usage_stmt = usage_stmt.where(Consumable.department_id.in_(visible_ids))
    usages = (await session.exec(usage_stmt)).all()

    for usage in usages:
        consumable_name = usage.consumable.name if usage.consumable else "(gelöschtes Material)"
        worker_name = usage.worker.full_name if usage.worker else "(gelöschter Mitarbeiter)"
        entries.append(HistoryEntry(
            timestamp=usage.used_at, action="entnommen", title=consumable_name, subtitle=worker_name,
            detail=f"{usage.quantity}x",
        ))

    if q:
        q_lower = q.lower()
        entries = [e for e in entries if q_lower in e.title.lower() or q_lower in e.subtitle.lower()]

    entries.sort(key=lambda e: e.timestamp, reverse=True)

    total = len(entries)
    start = (page - 1) * _PAGE_SIZE
    page_entries = entries[start:start + _PAGE_SIZE]
    has_more = start + _PAGE_SIZE < total

    return templates.TemplateResponse(
        request,
        "history/index.html",
        {
            "user": user, "entries": page_entries,
            "q": q, "page": page, "has_more": has_more, "total": total,
        },
    )
