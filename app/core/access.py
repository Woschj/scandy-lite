"""
Zentrale Berechtigungslogik: Rolle pro Benutzer UND Abteilung.

Admin ist ein globales Flag (User.is_admin) - kein Abteilungs-Eintrag nötig,
voller Zugriff überall. Für alle anderen bestimmt sich der Zugriff über
UserDepartmentRole: eine Person kann in mehreren Abteilungen jeweils eine
eigene Rolle haben (z.B. Mitarbeiter in Werkstatt, gleichzeitig Nutzer in Büro).
"""
import uuid

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.common import UserRole
from app.models.department import Department
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole


async def get_department_roles(session: AsyncSession, user: User) -> list[UserDepartmentRole]:
    """Alle Abteilungs-Rollen eines Users (leer für Admins - die brauchen keine,
    da global voller Zugriff)."""
    if user.is_admin:
        return []
    result = await session.exec(select(UserDepartmentRole).where(UserDepartmentRole.user_id == user.id))
    return list(result.all())


async def get_role_in_department(session: AsyncSession, user: User, department_id: uuid.UUID) -> UserRole | None:
    """Effektive Rolle eines Users in einer bestimmten Abteilung.
    Admin -> immer ADMIN (unabhängig von expliziten Einträgen).
    Sonst -> die für genau diese Abteilung hinterlegte Rolle, falls vorhanden."""
    if user.is_admin:
        return UserRole.ADMIN
    result = await session.exec(
        select(UserDepartmentRole).where(
            UserDepartmentRole.user_id == user.id, UserDepartmentRole.department_id == department_id
        )
    )
    role_entry = result.first()
    return role_entry.role if role_entry else None


async def is_staff_in_department(session: AsyncSession, user: User, department_id: uuid.UUID) -> bool:
    """Darf dieser User in dieser Abteilung verwalten/ausgeben (Admin oder Mitarbeiter-Rolle dort)?"""
    role = await get_role_in_department(session, user, department_id)
    return role in (UserRole.ADMIN, UserRole.MITARBEITER)


async def get_visible_department_ids(session: AsyncSession, user: User) -> list[uuid.UUID] | None:
    """Abteilungen, aus denen dieser User Gegenstände/Material sehen darf
    (jede Rolle - Mitarbeiter UND Nutzer - gewährt zumindest Sichtbarkeit).
    None = uneingeschränkt (Admin, wird von den Routen als 'alle Abteilungen,
    kein Filter' interpretiert)."""
    if user.is_admin:
        return None
    roles = await get_department_roles(session, user)
    return [r.department_id for r in roles]


async def get_accessible_departments(session: AsyncSession, user: User) -> list[Department]:
    """Für den Abteilungs-Switcher: die tatsächlichen Department-Objekte (nicht
    nur IDs), zu denen dieser User irgendeine Rolle hat. Admin sieht alle
    aktiven Abteilungen. Alphabetisch sortiert - wichtig für einen
    deterministischen Default (erste Abteilung), nicht nur für die Anzeige."""
    if user.is_admin:
        result = await session.exec(select(Department).where(Department.is_active == True).order_by(Department.name))  # noqa: E712
        return list(result.all())

    roles = await get_department_roles(session, user)
    dept_ids = [r.department_id for r in roles]
    if not dept_ids:
        return []
    result = await session.exec(select(Department).where(Department.id.in_(dept_ids)).order_by(Department.name))
    return list(result.all())
