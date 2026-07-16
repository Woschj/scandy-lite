"""
Lending = eine Ausleihe eines Gegenstands. `returned_at IS NULL` bedeutet:
aktuell ausgeliehen. Das ist die zentrale Tabelle für den Kern-Workflow und
gleichzeitig die Basis der Historie.

Bewusste Design-Entscheidung ggü. dem Original: hier gibt es EINE Quelle der Wahrheit
für "ist Gegenstand X gerade ausgeliehen" (offene Lending statt zusätzlichem Status-
Sync-Risiko). Ein DB-Constraint (siehe Migration) stellt sicher, dass pro Gegenstand
max. eine offene Lending existiert.
"""
import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Index, text
from sqlmodel import Field, Relationship

from app.models.common import TimestampMixin, new_uuid, utcnow

if TYPE_CHECKING:
    from app.models.department import Department
    from app.models.item import Item
    from app.models.user import User


class Lending(TimestampMixin, table=True):
    __tablename__ = "lendings"
    __table_args__ = (
        # Muss zur Migration bd20e573cbb2 passen (dort per rohem SQL
        # angelegt) - hier zusätzlich im Modell deklariert, damit
        # SQLModel.metadata.create_all (Tests, siehe tests/conftest.py) den
        # Schutz auch tatsächlich abbildet. Ohne das würde z.B. ein Test für
        # den IntegrityError-Handling-Pfad in pickup.py stillschweigend
        # erfolgreich durchlaufen, obwohl er in Postgres/Produktion an genau
        # diesem Constraint scheitern würde.
        Index(
            "uq_lendings_open_item", "item_id", unique=True,
            postgresql_where=text("returned_at IS NULL"),
            sqlite_where=text("returned_at IS NULL"),
        ),
    )

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    # Nullable, damit ein Gegenstand aus dem Papierkorb endgültig gelöscht
    # werden kann, ohne die Ausleih-Historie zu zerreißen (siehe
    # app/core/trash.py) - Name/Barcode werden dabei als Text-Schnappschuss
    # in den *_snapshot-Feldern erhalten, bevor die FK auf NULL gesetzt wird.
    item_id: uuid.UUID | None = Field(default=None, foreign_key="items.id", index=True)
    item: Optional["Item"] = Relationship(back_populates="lendings")
    item_name_snapshot: str | None = Field(default=None, max_length=200)
    item_barcode_snapshot: str | None = Field(default=None, max_length=100)

    worker_id: uuid.UUID | None = Field(default=None, foreign_key="users.id", index=True)
    worker: Optional["User"] = Relationship(back_populates="lendings")
    worker_name_snapshot: str | None = Field(default=None, max_length=200)

    # Denormalisiert für schnelle abteilungsgescopte Abfragen (spiegelt
    # item.department_id). Nullable aus demselben Grund wie item_id/worker_id
    # oben - eine Abteilung kann endgültig gelöscht werden (kaskadiert über
    # app/core/trash.py::purge_department), ohne die Historie zu zerreißen.
    department_id: uuid.UUID | None = Field(default=None, foreign_key="departments.id", index=True)
    department: Optional["Department"] = Relationship(back_populates="lendings")
    department_name_snapshot: str | None = Field(default=None, max_length=200)

    lent_at: datetime = Field(default_factory=utcnow, index=True)
    returned_at: datetime | None = Field(default=None, index=True)

    # Digitale Unterschrift bei der Ausgabe (base64 Data-URL, PNG vom Canvas-Pad).
    # Bewusst als Text in der Zeile statt separater Datei-Infrastruktur -
    # Unterschriften sind klein (~5-20 KB) und gehören untrennbar zur Ausleihe.
    signature: str | None = Field(default=None)

    @property
    def is_active(self) -> bool:
        return self.returned_at is None
