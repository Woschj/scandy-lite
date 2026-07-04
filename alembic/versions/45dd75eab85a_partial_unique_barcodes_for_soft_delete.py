"""partial unique barcodes for soft delete

Revision ID: 45dd75eab85a
Revises: f49c8660500c
Create Date: 2026-07-04 07:13:06.703464

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '45dd75eab85a'
down_revision: Union[str, None] = 'f49c8660500c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Problem: Barcode-Unique-Indizes umfassten auch soft-gelöschte Datensätze.
    # Folge: Barcode eines gelöschten Eintrags war nie wieder verwendbar -> 500er
    # beim Neuanlegen. Fix: Eindeutigkeit nur unter AKTIVEN (deleted_at IS NULL).
    for table in ("workers", "items", "consumables"):
        op.execute(f"DROP INDEX IF EXISTS ix_{table}_barcode")
        op.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS uq_{table}_barcode_active "
            f"ON {table} (barcode) WHERE deleted_at IS NULL"
        )


def downgrade() -> None:
    for table in ("workers", "items", "consumables"):
        op.execute(f"DROP INDEX IF EXISTS uq_{table}_barcode_active")
        op.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ix_{table}_barcode ON {table} (barcode)")
