"""
Consumable = Verbrauchsmaterial mit einem Bestand (quantity).
Anders als bei Tools gibt es keine "Rückgabe" - nur Entnahmen, die den Bestand reduzieren.
Jede Entnahme wird als ConsumableUsage protokolliert (-> Ausleih-Historie).
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import SoftDeleteMixin, TimestampMixin, new_uuid, utcnow

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.worker import Worker


class Consumable(TimestampMixin, SoftDeleteMixin, table=True):
    __tablename__ = "consumables"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    barcode: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(max_length=200)
    category: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)
    unit: str = Field(default="Stück", max_length=50)  # Stück, Liter, Meter, ...

    quantity: int = Field(default=0, ge=0)
    min_quantity: int = Field(default=0, ge=0)  # für spätere Mindestbestand-Warnung

    department_id: uuid.UUID = Field(foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship(back_populates="consumables")

    usages: list["ConsumableUsage"] = Relationship(back_populates="consumable")


class ConsumableUsage(TimestampMixin, table=True):
    """Protokoll jeder Entnahme - Grundlage für die Verbrauchsmaterial-Historie."""
    __tablename__ = "consumable_usages"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    consumable_id: uuid.UUID = Field(foreign_key="consumables.id", index=True)
    consumable: Optional["Consumable"] = Relationship(back_populates="usages")

    worker_id: uuid.UUID = Field(foreign_key="workers.id", index=True)
    worker: Optional["Worker"] = Relationship()

    quantity: int = Field(gt=0)
    used_at: datetime = Field(default_factory=utcnow, index=True)
