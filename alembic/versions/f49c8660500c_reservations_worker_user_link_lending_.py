"""reservations, worker user link, lending signature

Revision ID: f49c8660500c
Revises: bd20e573cbb2
Create Date: 2026-07-03 14:10:03.916765

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'f49c8660500c'
down_revision: Union[str, None] = 'bd20e573cbb2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'reservations',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('item_id', sa.Uuid(), nullable=False),
        sa.Column('worker_id', sa.Uuid(), nullable=False),
        sa.Column('department_id', sa.Uuid(), nullable=False),
        sa.Column('fulfilled_at', sa.DateTime(), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['item_id'], ['items.id']),
        sa.ForeignKeyConstraint(['worker_id'], ['workers.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_reservations_item_id'), 'reservations', ['item_id'], unique=False)
    op.create_index(op.f('ix_reservations_worker_id'), 'reservations', ['worker_id'], unique=False)
    op.create_index(op.f('ix_reservations_department_id'), 'reservations', ['department_id'], unique=False)
    # Max. eine OFFENE Reservierung pro Gegenstand (Race-Condition-Schutz wie bei Lendings)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_reservations_open_item "
        "ON reservations (item_id) WHERE fulfilled_at IS NULL AND cancelled_at IS NULL"
    )

    with op.batch_alter_table('workers') as batch_op:
        batch_op.add_column(sa.Column('user_id', sa.Uuid(), nullable=True))
        batch_op.create_unique_constraint('uq_workers_user_id', ['user_id'])
        batch_op.create_foreign_key('fk_workers_user_id', 'users', ['user_id'], ['id'])

    op.add_column('lendings', sa.Column('signature', sqlmodel.sql.sqltypes.AutoString(), nullable=True))


def downgrade() -> None:
    op.drop_column('lendings', 'signature')
    with op.batch_alter_table('workers') as batch_op:
        batch_op.drop_constraint('fk_workers_user_id', type_='foreignkey')
        batch_op.drop_constraint('uq_workers_user_id', type_='unique')
        batch_op.drop_column('user_id')
    op.execute("DROP INDEX IF EXISTS uq_reservations_open_item")
    op.drop_index(op.f('ix_reservations_department_id'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_worker_id'), table_name='reservations')
    op.drop_index(op.f('ix_reservations_item_id'), table_name='reservations')
    op.drop_table('reservations')
