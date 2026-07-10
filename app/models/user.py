"""
User = jemand mit einem Login.

Berechtigungsmodell: Admin ist ein globales Flag (is_admin) - Admins haben
vollen Zugriff auf alles, keine expliziten Abteilungs-Einträge nötig. Für
alle anderen bestimmt sich die Rolle PRO ABTEILUNG über UserDepartmentRole
(z.B. Mitarbeiter in Werkstatt, gleichzeitig Nutzer in Büro) - es gibt
bewusst KEINE globale Rolle und KEINE einzelne "Heimat-Abteilung" mehr auf
diesem Modell.

Wichtig für die spätere LDAP/SSO-Anbindung:
- `auth_source` unterscheidet, woher der User verwaltet wird.
- `hashed_password` ist NULLABLE, weil LDAP/SSO-User kein lokales Passwort haben.
- `external_id` kann später die LDAP-DN oder die SSO-Subject-ID aufnehmen.
Dadurch lässt sich LDAP/SSO andocken, ohne dieses Modell nochmal umzubauen -
es kommt nur ein neuer Auth-Provider hinzu, der User mit auth_source="ldap"/"sso" erzeugt/synct.
"""
import uuid

from sqlmodel import Field, Relationship

from app.models.common import AuthSource, TimestampMixin, new_uuid
from app.models.user_department_role import UserDepartmentRole


class User(TimestampMixin, table=True):
    __tablename__ = "users"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    username: str = Field(index=True, unique=True, max_length=100)
    email: str | None = Field(default=None, max_length=255)

    is_admin: bool = Field(default=False)
    auth_source: AuthSource = Field(default=AuthSource.LOCAL)

    # Nur gesetzt wenn auth_source == LOCAL
    hashed_password: str | None = Field(default=None)

    # Für LDAP/SSO: eindeutige externe Kennung (LDAP-DN, SSO-Subject/sAMAccountName, ...)
    external_id: str | None = Field(default=None, index=True, unique=True)

    is_active: bool = Field(default=True)

    department_roles: list["UserDepartmentRole"] = Relationship(back_populates="user")
