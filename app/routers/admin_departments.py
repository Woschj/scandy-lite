"""
Abteilungsverwaltung im Admin-Bereich: anlegen, aktivieren/deaktivieren,
kaskadierend löschen (siehe app/core/trash.py::purge_department).
"""
import uuid

from fastapi import APIRouter, Depends, Form
from fastapi.responses import RedirectResponse
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import populate_nav_context, require_admin, verify_csrf
from app.core.responses import redirect_with_query
from app.core.trash import purge_department
from app.models.department import Department
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


@router.post("/departments/new")
async def create_department(
    code: str = Form(...),
    name: str = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(select(Department).where(Department.code == code))
    if not result.first():
        session.add(Department(code=code.strip().lower(), name=name.strip()))
        await session.commit()
    return RedirectResponse(url="/admin/settings#departments", status_code=303)


@router.post("/departments/{department_id}/toggle")
async def toggle_department(
    department_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    department = await session.get(Department, department_id)
    if department:
        department.is_active = not department.is_active
        session.add(department)
        await session.commit()
    return RedirectResponse(url="/admin/settings#departments", status_code=303)


@router.post("/departments/{department_id}/delete")
async def delete_department(
    department_id: uuid.UUID,
    force: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Löscht die Abteilung KASKADIEREND (siehe app.core.trash.purge_department):
    Gegenstände/Verbrauchsmaterial/Benutzer/Kategorien/Standorte/Zugriffs-
    Zuweisungen der Abteilung werden mitgelöscht, abgeschlossene Ausleih-/
    Entnahme-/Reservierungs-Historie bleibt als Text-Schnappschuss erhalten
    (nie gelöscht). Blockiert NUR bei noch OFFENEN Ausleihen/Reservierungen/
    Material-Vormerkungen - das sind aktive Geschäftsvorgänge, keine reine
    Historie. Mit force=true werden diese stattdessen automatisch
    abgeschlossen statt zu blockieren (Testdaten/Fehleingaben aufräumen,
    ohne jede Zeile erst händisch suchen zu müssen - "Trotzdem entfernen" im UI)."""
    department = await session.get(Department, department_id)
    if not department:
        return RedirectResponse(url="/admin/settings#departments", status_code=303)

    name = department.name
    error = await purge_department(session, department, force=bool(force))
    if error:
        return redirect_with_query(
            "/admin/settings", fragment="departments",
            error=f"{error} Erst zurückgeben/stornieren, oder stattdessen nur deaktivieren.",
        )

    await session.commit()
    return redirect_with_query("/admin/settings", fragment="departments", ok=f"{name} gelöscht.")
