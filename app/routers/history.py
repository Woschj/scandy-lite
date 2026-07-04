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
from app.core.deps import get_current_department, get_current_user
from app.core.templating import templates
from app.models.consumable import Consumable, ConsumableUsage
from app.models.department import Department
from app.models.item import Item
from app.models.lending import Lending
from app.models.user import User

router = APIRouter(prefix="/history", tags=["history"])

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
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    entries: list[HistoryEntry] = []

    lending_stmt = (
        select(Lending)
        .options(selectinload(Lending.item), selectinload(Lending.worker))
        .order_by(Lending.lent_at.desc())
        .limit(_FETCH_LIMIT)
    )
    if department:
        lending_stmt = lending_stmt.where(Lending.department_id == department.id)
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
    if department:
        usage_stmt = usage_stmt.where(Consumable.department_id == department.id)
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
            "user": user, "department": department, "entries": page_entries,
            "q": q, "page": page, "has_more": has_more, "total": total,
        },
    )
