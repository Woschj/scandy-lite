"""
Historie - kombinierte, chronologische Zeitleiste aus Ausleihen, Rückgaben und
Verbrauchsmaterial-Entnahmen. Bewusst als EINE Ansicht statt getrennter
Tool-Historie/Worker-Historie/Consumable-Historie (wie im Original) - für ein
schlankes System reicht eine gemeinsame, filterbare Liste.

Ausleihen werden nach (Mitarbeiter, Unterschrift) GRUPPIERT statt einzeln
aufgelistet: eine Unterschrift gehört immer zu genau einem Bestätigungsvorgang
(egal ob Einzel-Ausgabe oder Sammel-Ausgabe für 20 Gegenstände auf einmal) -
das ist ein natürlicher, bereits vorhandener Gruppierungsschlüssel, ohne dass
wir dafür extra eine "Sitzung"/"Vorgang"-Tabelle bräuchten. Historische, aus
Scandy2 importierte Ausleihen ohne Unterschrift bleiben einzeln (Gruppierung
über eine gemeinsame NULL-Unterschrift wäre irreführend - würde sämtliche
Alt-Ausleihen einer Person fälschlich in einen Topf werfen).
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.access import get_visible_department_ids
from app.core.deps import get_current_user, populate_nav_context, require_staff
from app.core.templating import templates
from app.models.consumable import ConsumableUsage
from app.models.item import Item
from app.models.lending import Lending
from app.models.user import User

router = APIRouter(prefix="/history", tags=["history"], dependencies=[Depends(populate_nav_context), Depends(require_staff)])

_FETCH_LIMIT = 300  # pro Quelle - für ein internes Tool ausreichend, keine Pagination-API nötig
_PAGE_SIZE = 50


@dataclass
class LendingDetail:
    name: str
    lent_at: datetime
    returned_at: datetime | None


@dataclass
class HistoryEntry:
    timestamp: datetime
    action: str  # "ausgeliehen" | "entnommen" - fürs Icon/den Chip
    title: str
    subtitle: str  # Mitarbeitername
    detail: str = ""
    signature: str | None = None
    lending_items: list[LendingDetail] = field(default_factory=list)  # nur bei gruppierten Ausleihen
    open_count: int = 0
    total_count: int = 1

    @property
    def search_text(self) -> str:
        extra = " ".join(li.name for li in self.lending_items)
        return f"{self.title} {self.subtitle} {extra}".lower()


@router.get("")
async def history_index(
    request: Request,
    q: str = "",
    page: int = 1,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    # page=0 oder negativ (z.B. per manipuliertem Query-Parameter) würde sonst
    # über Pythons negative Slice-Indizierung ein falsches/leeres Ergebnis
    # liefern statt auf Seite 1 zu klemmen.
    page = max(page, 1)

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

    # Gruppieren nach (worker_id, signature) - siehe Modul-Docstring. Nur wenn
    # eine Unterschrift vorhanden ist; ohne Unterschrift (Alt-/Import-Daten)
    # bleibt jede Ausleihe ein eigener Eintrag.
    groups: dict[tuple, list[Lending]] = defaultdict(list)
    ungrouped: list[Lending] = []
    for lending in lendings:
        if lending.signature:
            groups[(lending.worker_id, lending.signature)].append(lending)
        else:
            ungrouped.append(lending)

    for (_worker_id, signature), group in groups.items():
        group.sort(key=lambda l: l.lent_at)
        worker_name = group[0].worker.full_name if group[0].worker else (group[0].worker_name_snapshot or "(gelöschter Mitarbeiter)")
        details = [
            LendingDetail(
                name=l.item.name if l.item else (l.item_name_snapshot or "(gelöschter Gegenstand)"),
                lent_at=l.lent_at, returned_at=l.returned_at,
            )
            for l in group
        ]
        open_count = sum(1 for l in group if l.returned_at is None)
        title = details[0].name if len(group) == 1 else f"{len(group)} Gegenstände"
        entries.append(HistoryEntry(
            timestamp=group[0].lent_at, action="ausgeliehen", title=title, subtitle=worker_name,
            signature=signature, lending_items=details, open_count=open_count, total_count=len(group),
        ))

    for lending in ungrouped:
        item_name = lending.item.name if lending.item else (lending.item_name_snapshot or "(gelöschter Gegenstand)")
        worker_name = lending.worker.full_name if lending.worker else (lending.worker_name_snapshot or "(gelöschter Mitarbeiter)")
        entries.append(HistoryEntry(
            timestamp=lending.lent_at, action="ausgeliehen", title=item_name, subtitle=worker_name,
            open_count=(1 if lending.returned_at is None else 0), total_count=1,
            lending_items=[LendingDetail(name=item_name, lent_at=lending.lent_at, returned_at=lending.returned_at)],
        ))

    usage_stmt = (
        select(ConsumableUsage)
        .options(selectinload(ConsumableUsage.consumable), selectinload(ConsumableUsage.worker))
        .order_by(ConsumableUsage.used_at.desc())
        .limit(_FETCH_LIMIT)
    )
    if visible_ids is not None:
        usage_stmt = usage_stmt.where(ConsumableUsage.department_id.in_(visible_ids))
    usages = (await session.exec(usage_stmt)).all()

    for usage in usages:
        consumable_name = usage.consumable.name if usage.consumable else (usage.consumable_name_snapshot or "(gelöschtes Material)")
        worker_name = usage.worker.full_name if usage.worker else (usage.worker_name_snapshot or "(gelöschter Mitarbeiter)")
        entries.append(HistoryEntry(
            timestamp=usage.used_at, action="entnommen", title=consumable_name, subtitle=worker_name,
            detail=f"{usage.quantity}x",
        ))

    if q:
        q_lower = q.lower()
        entries = [e for e in entries if q_lower in e.search_text]

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
