"""consumable quantity check constraint

Revision ID: c3f0a1b2d4e5
Revises: 31eca6e24ee2
Create Date: 2026-07-11 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'c3f0a1b2d4e5'
down_revision: Union[str, None] = '31eca6e24ee2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Defense-in-depth gegen negativen Bestand: die Anwendung sichert das
    # bereits über ein atomares UPDATE ... WHERE quantity-Guard ab (siehe
    # app/routers/scan.py scan_consume, app/routers/consumables.py
    # adjust_consumable), aber ein DB-Constraint fängt auch Zugriffe ab, die
    # nicht über diesen Code-Pfad laufen (z.B. manuelle SQL-Korrekturen).
    op.create_check_constraint(
        'ck_consumables_quantity_non_negative', 'consumables', 'quantity >= 0'
    )


def downgrade() -> None:
    op.drop_constraint('ck_consumables_quantity_non_negative', 'consumables', type_='check')
