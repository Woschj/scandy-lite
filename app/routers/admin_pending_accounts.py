"""
Ausstehende SSO-Konten (approved_at NULL) - eigene Seite statt Settings-Tab:
soll bei offenen Freischaltungen sofort ins Auge fallen (Link/Hinweis auf
der Übersicht, siehe app/routers/pages.py), nicht in den ohnehin schon
vollen Einstellungen untergehen.
"""
import uuid

from fastapi import APIRouter, Depends, Form, Request
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import populate_nav_context, require_admin, verify_csrf
from app.core.responses import redirect_with_query
from app.core.templating import templates
from app.core.trash import purge_user
from app.models.common import UserRole, utcnow
from app.models.department import Department
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


@router.get("/pending-accounts")
async def pending_accounts(
    request: Request,
    ok: str = "",
    error: str = "",
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    result = await session.exec(
        select(User).where(User.approved_at.is_(None), User.deleted_at.is_(None)).order_by(User.created_at)
    )
    pending = result.all()
    departments = (await session.exec(select(Department).where(Department.is_active == True).order_by(Department.name))).all()  # noqa: E712
    return templates.TemplateResponse(
        request, "admin/pending_accounts.html",
        {"user": user, "pending": pending, "departments": departments, "ok": ok, "error": error},
    )


@router.post("/pending-accounts/{user_id}/approve")
async def approve_pending_account(
    user_id: uuid.UUID,
    department_id: uuid.UUID = Form(...),
    initial_role: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Freischalten braucht IMMER eine Abteilung (anders als beim lokalen
    Anlegen, wo home_department_id auch schon Pflicht ist) - ohne Abteilung
    kann die Person nirgends etwas sehen, das Konto wäre freigeschaltet,
    aber praktisch nutzlos."""
    target = await session.get(User, user_id)
    if not target or target.approved_at is not None or target.deleted_at is not None:
        return redirect_with_query("/admin/pending-accounts", error="Konto nicht gefunden oder bereits bearbeitet.")

    target.department_id = department_id
    target.is_active = True
    target.approved_at = utcnow()
    session.add(target)
    await session.flush()  # target.id existiert schon (SSO-Konten werden beim ersten Login sofort committet)

    if initial_role in {UserRole.MITARBEITER.value, UserRole.NUTZER.value}:
        session.add(UserDepartmentRole(user_id=target.id, department_id=department_id, role=UserRole(initial_role)))

    await session.commit()
    return redirect_with_query("/admin/pending-accounts", ok=f"{target.full_name} freigeschaltet.")


@router.post("/pending-accounts/{user_id}/reject")
async def reject_pending_account(
    user_id: uuid.UUID,
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    """Löscht statt in den Papierkorb zu legen: ein noch nie freigeschaltetes
    Konto hat garantiert keine Historie (Ausleihen/Reservierungen setzen
    Zugriff voraus) - purge_user räumt trotzdem über den etablierten,
    getesteten Weg auf statt eine zweite Lösch-Logik zu bauen."""
    target = await session.get(User, user_id)
    if not target or target.approved_at is not None:
        return redirect_with_query("/admin/pending-accounts", error="Konto nicht gefunden oder bereits bearbeitet.")

    error = await purge_user(session, target, force=True)
    if error:
        return redirect_with_query("/admin/pending-accounts", error=error)
    await session.commit()
    return redirect_with_query("/admin/pending-accounts", ok="Konto abgelehnt und entfernt.")
