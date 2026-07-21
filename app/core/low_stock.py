"""
Tägliche Mindestbestand-Prüfung: sammelt Verbrauchsmaterial mit
quantity <= min_quantity und schickt eine Sammel-Mail an alle Admins mit
hinterlegter E-Mail-Adresse - macht aus dem passiven roten Chip in der Liste
eine aktive Benachrichtigung (sonst sieht das nur, wer zufällig durchscrollt).

Läuft als Hintergrund-Task ab app/main.py::lifespan, nicht als externer Cron -
kein zusätzlicher Dienst/Scheduler nötig für ein einzelnes internes Tool.
Bewusst kein persistierter "zuletzt geprüft"-Zeitstempel: die Schleife
schläft nach jedem Lauf bis zum nächsten Tag um _CHECK_HOUR Uhr, ein
Neustart mitten am Tag verschiebt den nächsten Lauf einfach auf den
nächsten Tag - für ein internes Werkstatt-Tool ausreichend genau, ohne
zusätzliche Tabelle/Zustand.
"""
import asyncio
import logging
from datetime import datetime, time, timedelta

from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import async_session_maker
from app.core.email import send_email
from app.core.templating import templates
from app.models.consumable import Consumable
from app.models.user import User

logger = logging.getLogger("scandy-lite")

_CHECK_HOUR = 6  # lokale Server-/Container-Zeit - früh morgens, vor Schichtbeginn


async def _collect_low_stock(session: AsyncSession) -> list[Consumable]:
    result = await session.exec(
        select(Consumable)
        .where(Consumable.deleted_at.is_(None), Consumable.quantity <= Consumable.min_quantity)
        .options(selectinload(Consumable.department))
        .order_by(Consumable.name)
    )
    return result.all()


async def run_low_stock_check() -> None:
    """Einmaliger Check + Versand - eigene Funktion (statt nur in der Schleife
    inline), damit sie sich isoliert testen lässt (siehe tests/test_low_stock.py)."""
    async with async_session_maker() as session:
        low_stock = await _collect_low_stock(session)
        if not low_stock:
            return

        admins = (
            await session.exec(
                select(User).where(
                    User.is_admin == True,  # noqa: E712
                    User.is_active == True,  # noqa: E712
                    User.deleted_at.is_(None),
                    User.email.is_not(None),
                )
            )
        ).all()
        if not admins:
            logger.warning(
                "Mindestbestand-Warnung: %d Artikel betroffen, aber kein Admin mit hinterlegter E-Mail-Adresse.",
                len(low_stock),
            )
            return

        html_body = templates.get_template("email/low_stock.html").render(items=low_stock)
        subject = f"Scandy-Lite: {len(low_stock)} Artikel unter Mindestbestand"
        for admin in admins:
            await send_email(session, admin.email, subject, html_body)


async def low_stock_check_loop() -> None:
    """Läuft dauerhaft im Hintergrund (als asyncio-Task aus main.py::lifespan
    gestartet): schläft bis zum nächsten _CHECK_HOUR Uhr, prüft, schläft wieder."""
    while True:
        now = datetime.now()
        next_run = datetime.combine(now.date(), time(hour=_CHECK_HOUR))
        if now >= next_run:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            await run_low_stock_check()
        except Exception:
            logger.exception("Mindestbestand-Prüfung fehlgeschlagen")
