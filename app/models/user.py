"""
User = jemand mit einem Login (Admin oder Mitarbeiter-Account).

Wichtig für die spätere LDAP/SSO-Anbindung:
- `auth_source` unterscheidet, woher der User verwaltet wird.
- `hashed_password` ist NULLABLE, weil LDAP/SSO-User kein lokales Passwort haben.
- `external_id` kann später die LDAP-DN oder die SSO-Subject-ID aufnehmen.
Dadurch lässt sich LDAP/SSO andocken, ohne dieses Modell nochmal umzubauen -
es kommt nur ein neuer Auth-Provider hinzu, der User mit auth_source="ldap"/"sso" erzeugt/synct.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import AuthSource, TimestampMixin, UserRole, new_uuid

if TYPE_CHECKING:
    from app.models.department import Department


class User(TimestampMixin, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=100)
    email: str | None = Field(default=None, max_length=255)

    role: UserRole = Field(default=UserRole.MITARBEITER)
    auth_source: AuthSource = Field(default=AuthSource.LOCAL)

    # Nur gesetzt wenn auth_source == LOCAL
    hashed_password: str | None = Field(default=None)

    # Für LDAP/SSO: eindeutige externe Kennung (LDAP-DN, SSO-Subject/sAMAccountName, ...)
    external_id: str | None = Field(default=None, index=True, unique=True)

    # Admins dürfen department_id = None haben -> sehen alle Abteilungen
    department_id: uuid.UUID | None = Field(default=None, foreign_key="departments.id")
    department: Optional["Department"] = Relationship(back_populates="users")

    is_active: bool = Field(default=True)
