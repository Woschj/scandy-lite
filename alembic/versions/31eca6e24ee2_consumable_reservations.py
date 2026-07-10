"""consumable reservations

Revision ID: 31eca6e24ee2
Revises: 980f814ad082
Create Date: 2026-07-10 19:44:40.247628

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '31eca6e24ee2'
down_revision: Union[str, None] = '980f814ad082'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'consumable_reservations',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('consumable_id', sa.Uuid(), nullable=False),
        sa.Column('worker_id', sa.Uuid(), nullable=False),
        sa.Column('department_id', sa.Uuid(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('fulfilled_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['consumable_id'], ['consumables.id']),
        sa.ForeignKeyConstraint(['worker_id'], ['workers.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_consumable_reservations_consumable_id'), 'consumable_reservations', ['consumable_id'], unique=False)
    op.create_index(op.f('ix_consumable_reservations_worker_id'), 'consumable_reservations', ['worker_id'], unique=False)
    op.create_index(op.f('ix_consumable_reservations_department_id'), 'consumable_reservations', ['department_id'], unique=False)
    # Bewusst KEIN Unique-Index auf offene Reservierungen wie bei Gegenständen -
    # Verbrauchsmaterial kann in Teilmengen von mehreren Personen gleichzeitig
    # angefragt werden, anders als ein einzelnes Exemplar eines Gegenstands.


def downgrade() -> None:
    op.drop_index(op.f('ix_consumable_reservations_department_id'), table_name='consumable_reservations')
    op.drop_index(op.f('ix_consumable_reservations_worker_id'), table_name='consumable_reservations')
    op.drop_index(op.f('ix_consumable_reservations_consumable_id'), table_name='consumable_reservations')
    op.drop_table('consumable_reservations')
