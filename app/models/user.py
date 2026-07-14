"""
User = jemand mit einem Login UND/ODER einem Mitarbeiter-Ausweis (Barcode,
zum Ausleihen/Reservieren) - beides ist bewusst dieselbe Entität, da
praktisch jeder, der ausleiht, früher oder später auch einen Login braucht
(vorher als getrenntes `Worker`-Modell geführt, was ständig zu Verwirrung
beim Verknüpfen führte). `hashed_password` bleibt NULL für reine
Ausweis-Inhaber ohne Login - Barcode-Scan (Ausleihe, Sammel-Abholung,
Verbrauchsmaterial-Entnahme) funktioniert weiterhin ohne Login.

Berechtigungsmodell: Admin ist ein globales Flag (is_admin) - Admins haben
vollen Zugriff auf alles, keine expliziten Abteilungs-Einträge nötig. Für
alle anderen bestimmt sich die Rolle PRO ABTEILUNG über UserDepartmentRole
(z.B. Mitarbeiter in Werkstatt, gleichzeitig Nutzer in Büro) - `department_id`
ist NUR die organisatorische "Heimat" des Ausweis-Datensatzes (wer ihn
verwaltet), gewährt für sich genommen KEINEN Zugriff.

Wichtig für die spätere LDAP/SSO-Anbindung:
- `auth_source` unterscheidet, woher der User verwaltet wird.
- `hashed_password` ist NULLABLE, weil LDAP/SSO-User kein lokales Passwort haben.
- `external_id` kann später die LDAP-DN oder die SSO-Subject-ID aufnehmen.
Dadurch lässt sich LDAP/SSO andocken, ohne dieses Modell nochmal umzubauen -
es kommt nur ein neuer Auth-Provider hinzu, der User mit auth_source="ldap"/"sso" erzeugt/synct.

Soft-Delete (statt hartem Löschen wie früher bei User): jetzt hängt
Ausleih-/Reservierungs-Historie (Lending.worker_id etc.) direkt am User -
endgültiges Löschen läuft über den Papierkorb (app/core/trash.py), der
Name/Barcode als Text-Schnappschuss in der Historie erhält, bevor die FK auf
NULL gesetzt wird.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import AuthSource, SoftDeleteMixin, TimestampMixin, new_uuid
from app.models.user_department_role import UserDepartmentRole

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.lending import Lending


class User(TimestampMixin, SoftDeleteMixin, table=True):
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

    # Ausweis-Felder (frueher Worker) - alle optional, da nicht jeder Login
    # (z.B. ein reiner Admin-Systemzugang) auch ein Ausweisinhaber ist.
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    barcode: str | None = Field(default=None, index=True, max_length=100)  # Eindeutigkeit: partieller Unique-Index (nur aktive Datensätze), s. Migration b6f1c9a4d2e7
    department_id: uuid.UUID | None = Field(default=None, foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship(back_populates="users")

    lendings: list["Lending"] = Relationship(back_populates="worker")

    department_roles: list["UserDepartmentRole"] = Relationship(back_populates="user")

    @property
    def full_name(self) -> str:
        if self.first_name or self.last_name:
            return f"{self.first_name or ''} {self.last_name or ''}".strip()
        return self.username
