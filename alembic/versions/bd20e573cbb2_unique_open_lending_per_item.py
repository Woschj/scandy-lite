"""unique open lending per item

Revision ID: bd20e573cbb2
Revises: 286deb5ad7fb
Create Date: 2026-07-02 18:11:06.257677

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'bd20e573cbb2'
down_revision: Union[str, None] = '286deb5ad7fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Erzwingt auf DB-Ebene: pro Gegenstand maximal EINE offene Ausleihe.
    # Schützt gegen Race-Conditions (zwei gleichzeitige Scans desselben Items),
    # die die Anwendungslogik allein nicht abfangen kann.
    # Partial Unique Index - von PostgreSQL und SQLite unterstützt.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_lendings_open_item "
        "ON lendings (item_id) WHERE returned_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_lendings_open_item")
