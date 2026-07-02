"""
Abteilungen (Departments) - die zentrale Mandantentrennung.
Jeder Gegenstand, Consumable, Worker und jede Lending gehört zu genau einer Abteilung.
Admins können abteilungsübergreifend agieren, Mitarbeiter sind auf ihre Abteilung gescoped.
"""
import uuid
from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship

from app.models.common import TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.consumable import Consumable
    from app.models.item import Item
    from app.models.lending import Lending
    from app.models.user import User
    from app.models.worker import Worker


class Department(TimestampMixin, table=True):
    __tablename__ = "departments"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    code: str = Field(index=True, unique=True, max_length=50)  # z.B. "werkstatt", "verwaltung"
    name: str = Field(max_length=200)
    is_active: bool = Field(default=True)

    # Beziehungen
    users: list["User"] = Relationship(back_populates="department")
    workers: list["Worker"] = Relationship(back_populates="department")
    items: list["Item"] = Relationship(back_populates="department")
    consumables: list["Consumable"] = Relationship(back_populates="department")
    lendings: list["Lending"] = Relationship(back_populates="department")
