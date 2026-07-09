"""
Worker = die Person, die physisch Werkzeug/Material ausleiht (z.B. per Barcode-Ausweis).
Bewusst getrennt von `User` (Systemzugang), weil nicht jeder, der ausleiht,
zwingend einen Login braucht - genau wie im Originalsystem.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import SoftDeleteMixin, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.group import WorkerGroup
    from app.models.lending import Lending


class Worker(TimestampMixin, SoftDeleteMixin, table=True):
    __tablename__ = "workers"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    barcode: str = Field(index=True, max_length=100)  # Eindeutigkeit: partieller Unique-Index (nur aktive Datensätze), s. Migration 45dd75eab85a
    first_name: str = Field(max_length=100)
    last_name: str = Field(max_length=100)

    # "Heimat"-Abteilung: organisatorische Zuordnung (z.B. wer diesen Mitarbeiter-
    # Datensatz verwaltet). Bestimmt NICHT mehr, welche Gegenstände ein Nutzer
    # sehen/reservieren darf, wenn eine Gruppe zugewiesen ist (siehe group_id).
    department_id: uuid.UUID = Field(foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship(back_populates="workers")

    # Bestimmt bei Nutzer-Workern, AUS WELCHEN ABTEILUNGEN sie ausleihen dürfen
    # (über GroupDepartmentAccess) - unabhängig von department_id. Optional:
    # ohne Gruppe fällt die Berechtigung auf die eigene department_id zurück
    # (Rückwärtskompatibilität für bestehende Mitarbeiter-Datensätze).
    group_id: uuid.UUID | None = Field(default=None, foreign_key="worker_groups.id")
    group: Optional["WorkerGroup"] = Relationship(back_populates="workers")

    # Optionale Verknüpfung zu einem System-Login: erlaubt es dem eingeloggten
    # Nutzer, für "seinen" Ausweis zu reservieren. Nicht jeder Worker braucht
    # einen Login (Ausleihe per Barcode geht weiterhin ohne).
    user_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", unique=True)

    is_active: bool = Field(default=True)

    lendings: list["Lending"] = Relationship(back_populates="worker")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
