"""
Nutzergruppen entkoppeln "wer darf was ausleihen" von "wo ein Gegenstand
organisatorisch hingehört". Ein Gegenstand gehört weiterhin zu genau einer
Abteilung (Inventar-Zuordnung, für Mitarbeiter-Verwaltung). Eine Gruppe (z.B.
"Studierende Informatik") bekommt Zugriff auf beliebig viele Abteilungen -
ihre Mitglieder (Worker) sehen und reservieren dann Gegenstände aus GENAU
diesen Abteilungen, unabhängig von ihrer eigenen "Heimat"-Abteilung.

Bewusst schlank: eine Gruppe pro Worker (kein voller M:N-Dschungel), aber
eine Gruppe kann Zugriff auf mehrere Abteilungen haben (M:N über
GroupDepartmentAccess).
"""
import uuid
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import TimestampMixin, new_uuid

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.worker import Worker


class WorkerGroup(TimestampMixin, table=True):
    __tablename__ = "worker_groups"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    name: str = Field(max_length=200, unique=True)

    workers: list["Worker"] = Relationship(back_populates="group")
    department_links: list["GroupDepartmentAccess"] = Relationship(back_populates="group")


class GroupDepartmentAccess(TimestampMixin, table=True):
    """Verknüpfungstabelle: welche Abteilungen darf eine Gruppe ausleihen."""
    __tablename__ = "group_department_access"

    group_id: uuid.UUID = Field(foreign_key="worker_groups.id", primary_key=True)
    department_id: uuid.UUID = Field(foreign_key="departments.id", primary_key=True)

    group: Optional["WorkerGroup"] = Relationship(back_populates="department_links")
    department: Optional["Department"] = Relationship()
