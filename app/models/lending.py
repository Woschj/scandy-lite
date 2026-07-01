"""
Lending = eine Werkzeug-Ausleihe. `returned_at IS NULL` bedeutet: aktuell ausgeliehen.
Das ist die zentrale Tabelle für den Kern-Workflow und gleichzeitig die Basis der Historie.

Bewusste Design-Entscheidung ggü. dem Original: hier gibt es EINE Quelle der Wahrheit
für "ist Tool X gerade ausgeliehen" (offene Lending statt zusätzlichem Status-Sync-Risiko).
Ein DB-Constraint (siehe Migration) stellt sicher, dass pro Tool max. eine offene Lending existiert.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship

from app.models.common import TimestampMixin, new_uuid, utcnow

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.tool import Tool
    from app.models.worker import Worker


class Lending(TimestampMixin, table=True):
    __tablename__ = "lendings"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    tool_id: uuid.UUID = Field(foreign_key="tools.id", index=True)
    tool: Optional["Tool"] = Relationship(back_populates="lendings")

    worker_id: uuid.UUID = Field(foreign_key="workers.id", index=True)
    worker: Optional["Worker"] = Relationship(back_populates="lendings")

    # Denormalisiert für schnelle abteilungsgescopte Abfragen (spiegelt tool.department_id)
    department_id: uuid.UUID = Field(foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship(back_populates="lendings")

    lent_at: datetime = Field(default_factory=utcnow, index=True)
    returned_at: datetime | None = Field(default=None, index=True)

    @property
    def is_active(self) -> bool:
        return self.returned_at is None
