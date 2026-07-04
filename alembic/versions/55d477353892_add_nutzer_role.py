"""add nutzer role

Revision ID: 55d477353892
Revises: 45dd75eab85a
Create Date: 2026-07-04 14:53:42.256580

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '55d477353892'
down_revision: Union[str, None] = '45dd75eab85a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'NUTZER'")


def downgrade() -> None:
    # Postgres kann einzelne Enum-Werte nicht per ALTER TYPE wieder entfernen
    # (nur den ganzen Typ neu anlegen und alle abhängigen Spalten migrieren).
    # Für dieses lokale Tool bewusst nicht automatisiert - falls ein Downgrade
    # nötig wird: zuerst sicherstellen, dass kein User mehr role='nutzer' hat.
    pass
