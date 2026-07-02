"""
Startseite nach dem Login. Phase 2 lieferte nur das Gerüst (Nav, Abteilungs-
Kontext, Design-System). Phase 3 zeigt hier bereits echte Kennzahlen.
"""
from fastapi import APIRouter, Depends, Request
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_department, get_current_user
from app.core.templating import templates
from app.models.consumable import Consumable
from app.models.department import Department
from app.models.item import Item
from app.models.user import User
from app.models.worker import Worker

router = APIRouter(tags=["pages"])


@router.get("/")
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    department: Department | None = Depends(get_current_department),
    session: AsyncSession = Depends(get_session),
):
    all_departments = None
    if user.role.value == "admin":
        result = await session.exec(select(Department).where(Department.is_active == True))  # noqa: E712
        all_departments = result.all()

    item_count = 0
    consumable_count = 0
    worker_count = 0
    if department:
        result = await session.exec(
            select(func.count()).select_from(Item).where(
                Item.department_id == department.id, Item.deleted_at.is_(None)
            )
        )
        item_count = result.one()

        result = await session.exec(
            select(func.count()).select_from(Consumable).where(
                Consumable.department_id == department.id, Consumable.deleted_at.is_(None)
            )
        )
        consumable_count = result.one()

        result = await session.exec(
            select(func.count()).select_from(Worker).where(
                Worker.department_id == department.id, Worker.deleted_at.is_(None)
            )
        )
        worker_count = result.one()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "department": department,
            "all_departments": all_departments,
            "item_count": item_count,
            "consumable_count": consumable_count,
            "worker_count": worker_count,
        },
    )
