"""
Item (Gegenstand) = ein einzelner, eindeutig per Barcode identifizierbarer
Gegenstand (Werkzeug, Gerät, Ausrüstung - bewusst neutral statt "Werkzeug",
da nicht jede Abteilung zwingend Werkzeuge im engeren Sinn ausleiht).

Der aktuelle Ausleihstatus ergibt sich aus `status` + der offenen Lending
(kein doppeltes Buchhalten - `status` wird beim Ausleihen/Zurückgeben synchron
mit der Lending-Tabelle aktualisiert, siehe LendingService in Phase 4).
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import ItemStatus, SoftDeleteMixin, TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.lending import Lending


class Item(TimestampMixin, SoftDeleteMixin, table=True):
    __tablename__ = "items"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    barcode: str = Field(index=True, max_length=100)  # Eindeutigkeit: partieller Unique-Index (nur aktive Datensätze), s. Migration 45dd75eab85a
    name: str = Field(max_length=200)
    category: str | None = Field(default=None, index=True, max_length=100)
    location: str | None = Field(default=None, index=True, max_length=100)
    notes: str | None = Field(default=None, max_length=2000)

    status: ItemStatus = Field(default=ItemStatus.VERFUEGBAR, index=True)

    department_id: uuid.UUID = Field(foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship(back_populates="items")

    lendings: list["Lending"] = Relationship(back_populates="item")
