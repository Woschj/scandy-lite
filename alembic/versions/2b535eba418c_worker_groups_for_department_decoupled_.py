"""worker groups for department-decoupled borrowing permissions

Revision ID: 2b535eba418c
Revises: 55d477353892
Create Date: 2026-07-04 15:20:55.970371

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '2b535eba418c'
down_revision: Union[str, None] = '55d477353892'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'worker_groups',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )

    op.create_table(
        'group_department_access',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('group_id', sa.Uuid(), nullable=False),
        sa.Column('department_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['group_id'], ['worker_groups.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('group_id', 'department_id'),
    )

    with op.batch_alter_table('workers') as batch_op:
        batch_op.add_column(sa.Column('group_id', sa.Uuid(), nullable=True))
        batch_op.create_foreign_key('fk_workers_group_id', 'worker_groups', ['group_id'], ['id'])


def downgrade() -> None:
    with op.batch_alter_table('workers') as batch_op:
        batch_op.drop_constraint('fk_workers_group_id', type_='foreignkey')
        batch_op.drop_column('group_id')

    op.drop_table('group_department_access')
    op.drop_table('worker_groups')
