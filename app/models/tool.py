"""
Tool = ein einzelnes, eindeutig per Barcode identifizierbares Werkzeug.
Der aktuelle Ausleihstatus ergibt sich aus `status` + der offenen Lending
(kein doppeltes Buchhalten - `status` wird beim Ausleihen/Zurückgeben synchron
mit der Lending-Tabelle aktualisiert, siehe LendingService in Phase 3).
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import SoftDeleteMixin, TimestampMixin, ToolStatus, new_uuid

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.lending import Lending


class Tool(TimestampMixin, SoftDeleteMixin, table=True):
    __tablename__ = "tools"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    barcode: str = Field(index=True, unique=True, max_length=100)
    name: str = Field(max_length=200)
    category: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=100)

    status: ToolStatus = Field(default=ToolStatus.VERFUEGBAR)

    department_id: uuid.UUID = Field(foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship(back_populates="tools")

    lendings: list["Lending"] = Relationship(back_populates="tool")
