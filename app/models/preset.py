"""
Kategorien und Standorte - abteilungsgebundene Vorschlagslisten für die
Gegenstands-/Verbrauchsmaterial-Formulare (Datalist-Autocomplete).

Bewusst KEIN Fremdschlüssel auf Item/Consumable: category/location bleiben dort
freie Textfelder, diese Tabellen liefern nur Admin-kuratierte Vorschläge fürs
Formular (genau wie im Original scandy2). Das hält Migrationen einfach und
verhindert, dass ein gelöschter Preset plötzlich bestehende Gegenstände verwaist.
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.department import Department


class Category(TimestampMixin, table=True):
    __tablename__ = "categories"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    name: str = Field(max_length=100)
    department_id: uuid.UUID = Field(foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship()


class Location(TimestampMixin, table=True):
    __tablename__ = "locations"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    name: str = Field(max_length=100)
    department_id: uuid.UUID = Field(foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship()
