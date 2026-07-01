"""
Startseite nach dem Login. Phase 2 liefert nur das Gerüst (Nav, Abteilungs-Kontext,
Design-System) - die eigentlichen Werkzeug-/Verbrauchsmaterial-Listen kommen in Phase 3/4.
"""
from fastapi import APIRouter, Depends, Request
from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.database import get_session
from app.core.deps import get_current_department, get_current_user
from app.core.templating import templates
from app.models.department import Department
from app.models.tool import Tool
from app.models.user import User

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

    tool_count = 0
    if department:
        result = await session.exec(
            select(func.count()).select_from(Tool).where(
                Tool.department_id == department.id, Tool.deleted_at.is_(None)
            )
        )
        tool_count = result.one()

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "user": user,
            "department": department,
            "all_departments": all_departments,
            "tool_count": tool_count,
        },
    )
