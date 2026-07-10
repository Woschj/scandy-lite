"""
Ersetzt das frühere Gruppen-Konzept (WorkerGroup/GroupDepartmentAccess)
vollständig. Statt "Nutzer gehört zu einer Gruppe, Gruppe hat Zugriff auf
Abteilungen" jetzt direkt: "Nutzer hat eine Rolle in einer Abteilung".

Ein User kann in mehreren Abteilungen jeweils eine eigene Rolle haben, z.B.
Mitarbeiter in Werkstatt UND Nutzer in Büro gleichzeitig. Admin bleibt ein
globales Flag auf User (siehe User.is_admin) - Admin braucht keine expliziten
Einträge hier, da global vollzugriff.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import TimestampMixin, UserRole

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.user import User


class UserDepartmentRole(TimestampMixin, table=True):
    __tablename__ = "user_department_roles"

    user_id: uuid.UUID = Field(foreign_key="users.id", primary_key=True)
    department_id: uuid.UUID = Field(foreign_key="departments.id", primary_key=True)
    role: UserRole = Field()  # MITARBEITER oder NUTZER - ADMIN ergibt hier keinen Sinn (global)

    user: Optional["User"] = Relationship(back_populates="department_roles")
    department: Optional["Department"] = Relationship()
