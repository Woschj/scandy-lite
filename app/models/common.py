"""
Gemeinsame Bausteine für alle Modelle: Enums, Timestamp-Mixin, Soft-Delete-Mixin.
"""
import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlmodel import Field, SQLModel


def new_uuid() -> uuid.UUID:
    return uuid.uuid4()


def utcnow() -> datetime:
    """Naive UTC - bewusst OHNE tzinfo, weil alle Spalten TIMESTAMP WITHOUT
    TIME ZONE sind und asyncpg aware datetimes dafür ablehnt. Alle Zeitstempel
    im System laufen über diese eine Funktion, damit naive/aware nie gemischt wird."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AuthSource(str, Enum):
    """Woher stammt der User? Phase 1: nur LOCAL. LDAP/SSO kommen später hinzu,
    ohne dass sich am restlichen Modell etwas ändern muss."""
    LOCAL = "local"
    LDAP = "ldap"
    SSO = "sso"


class UserRole(str, Enum):
    ADMIN = "admin"
    MITARBEITER = "mitarbeiter"
    NUTZER = "nutzer"  # Ansehen + Reservieren, keine Verwaltung/Ausgabe


class ItemStatus(str, Enum):
    VERFUEGBAR = "verfuegbar"
    AUSGELIEHEN = "ausgeliehen"
    DEFEKT = "defekt"
    AUSGEMUSTERT = "ausgemustert"


class CustomFieldType(str, Enum):
    """Typ eines admin-definierten Zusatzfelds (siehe app.models.custom_field) -
    bestimmt sowohl den Eingabetyp im Formular als auch die Validierung beim
    Speichern (app.core.custom_fields.save_values_for_item)."""
    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    SELECT = "select"


class TimestampMixin(SQLModel):
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False, sa_column_kwargs={"onupdate": utcnow})


class SoftDeleteMixin(SQLModel):
    deleted_at: datetime | None = Field(default=None, nullable=True)

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
