"""
ConsumableReservation = ein Nutzer merkt eine Menge Verbrauchsmaterial zur
Abholung/Entnahme vor. Parallel zu Reservation (Gegenstände), aber mit
Menge - anders als Gegenstände (ein Exemplar, exklusiv reserviert) kann
Verbrauchsmaterial in Teilmengen von MEHREREN Personen gleichzeitig
angefragt werden.

Bewusst als "weiche" Vormerkung: anders als bei Gegenständen wird der
Bestand NICHT hart reserviert/blockiert (kein Lagerbestand-Held) - Personal
sieht die offene Vormerkung beim Scannen und kann nach eigenem Ermessen
entscheiden. Das vermeidet die Komplexität von "Bestand minus Summe aller
offenen Reservierungen" bei gleichzeitigen Anfragen.

Offen = fulfilled_at UND cancelled_at sind NULL (gleiche Logik wie bei
Reservation/Lending).
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.consumable import Consumable
    from app.models.department import Department
    from app.models.user import User


class ConsumableReservation(TimestampMixin, table=True):
    __tablename__ = "consumable_reservations"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    # Nullable + Text-Schnappschuss aus demselben Grund wie bei Lending
    # (siehe app/models/lending.py) - endgültiges Löschen aus dem Papierkorb
    # (app/core/trash.py) darf die Vormerkungs-Historie nicht zerreißen.
    consumable_id: uuid.UUID | None = Field(default=None, foreign_key="consumables.id", index=True)
    consumable: Optional["Consumable"] = Relationship()
    consumable_name_snapshot: str | None = Field(default=None, max_length=200)
    consumable_barcode_snapshot: str | None = Field(default=None, max_length=100)

    worker_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)
    worker: Optional["User"] = Relationship()
    worker_name_snapshot: str | None = Field(default=None, max_length=200)

    department_id: uuid.UUID | None = Field(default=None, foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship()
    department_name_snapshot: str | None = Field(default=None, max_length=200)

    quantity: int = Field(gt=0)

    fulfilled_at: datetime | None = Field(default=None)   # in Entnahme überführt
    cancelled_at: datetime | None = Field(default=None)   # storniert

    @property
    def is_open(self) -> bool:
        return self.fulfilled_at is None and self.cancelled_at is None
