"""
Reservation = ein Nutzer merkt einen Gegenstand zur Abholung vor.
Offen = fulfilled_at UND cancelled_at sind NULL (gleiche Logik wie bei Lending:
eine Quelle der Wahrheit statt Status-Feld-Sync). Ein partieller Unique-Index
(Migration) erzwingt max. eine offene Reservierung pro Gegenstand.

Der Gegenstand bleibt dabei physisch VERFUEGBAR - "reserviert" wird aus der
offenen Reservierung abgeleitet, nicht als Item-Status dupliziert.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.item import Item
    from app.models.worker import Worker


class Reservation(TimestampMixin, table=True):
    __tablename__ = "reservations"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    # Nullable + Text-Schnappschuss aus demselben Grund wie bei Lending
    # (siehe app/models/lending.py) - endgültiges Löschen aus dem Papierkorb
    # (app/core/trash.py) darf die Reservierungs-Historie nicht zerreißen.
    item_id: uuid.UUID | None = Field(default=None, foreign_key="items.id", index=True)
    item: Optional["Item"] = Relationship()
    item_name_snapshot: str | None = Field(default=None, max_length=200)
    item_barcode_snapshot: str | None = Field(default=None, max_length=100)

    worker_id: uuid.UUID | None = Field(default=None, foreign_key="workers.id", index=True)
    worker: Optional["Worker"] = Relationship()
    worker_name_snapshot: str | None = Field(default=None, max_length=200)

    department_id: uuid.UUID = Field(foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship()

    fulfilled_at: datetime | None = Field(default=None)   # in Ausleihe überführt
    cancelled_at: datetime | None = Field(default=None)   # storniert

    @property
    def is_open(self) -> bool:
        return self.fulfilled_at is None and self.cancelled_at is None
