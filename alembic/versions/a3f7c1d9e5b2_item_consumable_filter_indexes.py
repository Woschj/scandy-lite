"""indexes for item/consumable filter columns

Gegenstände-/Verbrauchsmaterial-Listen (app/routers/items.py,
app/routers/consumables.py) filtern/sortieren über status, category,
location bzw. quantity, category, location - bislang ohne Index, mit
wachsender Zeilenzahl ein Full-Table-Scan pro Listenaufruf. Reine
CREATE INDEX-Migration, keine Datenumformung - risikoarm.

Revision ID: a3f7c1d9e5b2
Revises: 0f66012f02e8
Create Date: 2026-07-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a3f7c1d9e5b2'
down_revision: Union[str, None] = '0f66012f02e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('ix_items_status', 'items', ['status'])
    op.create_index('ix_items_category', 'items', ['category'])
    op.create_index('ix_items_location', 'items', ['location'])
    op.create_index('ix_consumables_quantity', 'consumables', ['quantity'])
    op.create_index('ix_consumables_category', 'consumables', ['category'])
    op.create_index('ix_consumables_location', 'consumables', ['location'])


def downgrade() -> None:
    op.drop_index('ix_consumables_location', table_name='consumables')
    op.drop_index('ix_consumables_category', table_name='consumables')
    op.drop_index('ix_consumables_quantity', table_name='consumables')
    op.drop_index('ix_items_location', table_name='items')
    op.drop_index('ix_items_category', table_name='items')
    op.drop_index('ix_items_status', table_name='items')
