"""
Admin-definierbare Zusatzfelder pro Kategorie (z.B. "MAC-Adresse" bei
Kategorie "Laptops") - siehe migrations_legacy/README.md, das entsprach im
alten Scandy2 den "Custom Fields", die beim Zuschnitt von Scandy-Lite bewusst
weggelassen wurden und hier gezielt (nur für Gegenstände, pro Kategorie)
nachgeholt werden.

CustomFieldDefinition hängt an einer konkreten Category-Zeile (FK), auch wenn
Item.category selbst weiterhin ein freies Textfeld ohne FK bleibt (siehe
app/models/preset.py) - welche Definitionen für einen Gegenstand gelten, wird
zur Laufzeit über Category.name == item.category (+ department) aufgelöst,
siehe app/core/custom_fields.py.
"""
import uuid

from sqlmodel import Field, UniqueConstraint

from app.models.common import CustomFieldType, TimestampMixin, new_uuid


class CustomFieldDefinition(TimestampMixin, table=True):
    __tablename__ = "custom_field_definitions"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    category_id: uuid.UUID = Field(foreign_key="categories.id", index=True)
    name: str = Field(max_length=100)
    field_type: CustomFieldType = Field(default=CustomFieldType.TEXT)
    options: str | None = Field(default=None)  # komma-getrennte Liste, nur bei SELECT

    # Firmeninterna vs. öffentlich sichtbar - analog zur bestehenden
    # can_manage-Regel für Status/Mindestbestand, aber PRO FELD wählbar statt
    # pauschal versteckt (manche Zusatzfelder sind harmlos, andere nicht).
    visible_to_all: bool = Field(default=False)


class CustomFieldValue(TimestampMixin, table=True):
    __tablename__ = "custom_field_values"
    __table_args__ = (UniqueConstraint("item_id", "field_id", name="uq_custom_field_values_item_field"),)

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    item_id: uuid.UUID = Field(foreign_key="items.id", index=True)
    field_id: uuid.UUID = Field(foreign_key="custom_field_definitions.id", index=True)
    value: str | None = Field(default=None)
