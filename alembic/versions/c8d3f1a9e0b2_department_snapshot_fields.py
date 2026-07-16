"""department nullable FKs + name snapshots for history tables

Ermöglicht das kaskadierende Löschen einer Abteilung
(app/core/trash.py::purge_department): abgeschlossene Historien-Zeilen
(Lending/Reservation/ConsumableUsage/ConsumableReservation) behalten den
Abteilungsnamen als Text-Schnappschuss, die FK-Spalte wird auf NULL
gesetzt - gleiches Muster wie die item_name_snapshot/worker_name_snapshot-
Felder aus Migration 5e8a2c1f9b6d.

Revision ID: c8d3f1a9e0b2
Revises: b6f1c9a4d2e7
Create Date: 2026-07-16 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c8d3f1a9e0b2'
down_revision: Union[str, None] = 'b6f1c9a4d2e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = ("lendings", "reservations", "consumable_usages", "consumable_reservations")


def upgrade() -> None:
    for table in _TABLES:
        op.alter_column(table, 'department_id', existing_type=sa.Uuid(), nullable=True)
        op.add_column(table, sa.Column('department_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, 'department_name_snapshot')
        op.alter_column(table, 'department_id', existing_type=sa.Uuid(), nullable=False)
