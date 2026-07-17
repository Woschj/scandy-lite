"""
Mitarbeiterausweis: eigener Barcode als QR-Code, wahlweise ausgedruckt oder
als Vollbild-Ansicht auf dem Handy zur Identifikation. Der QR-Code kodiert
exakt denselben Wert, den ein Scan-Vorgang per Kamera/Handscanner sonst aus
dem physischen Barcode/Ausweis liest (siehe app.core.barcodes) - Ausweis und
"echter" Barcode sind also immer deckungsgleich, keine zweite Quelle der
Wahrheit.

Admin-Variante (beliebigen Benutzer-Ausweis ansehen/drucken) liegt bewusst
bei app.routers.admin_settings, nicht hier - dort ist schon die gesamte
Benutzerverwaltung, dieser Router bleibt rein für die Selbstbedienungs-Ansicht.
"""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import selectinload
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.badge import qr_data_uri
from app.core.database import get_session
from app.core.deps import get_current_user, populate_nav_context
from app.core.templating import templates
from app.models.user import User

router = APIRouter(tags=["badge"], dependencies=[Depends(populate_nav_context)])


@router.get("/me/ausweis")
async def my_badge(
    request: Request,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(
        select(User).where(User.id == user.id).options(selectinload(User.department))
    )
    target = result.first()
    qr = qr_data_uri(target.barcode) if target.barcode else None
    return templates.TemplateResponse(
        request, "badge.html",
        {"user": user, "target": target, "qr": qr, "back_url": "/"},
    )
