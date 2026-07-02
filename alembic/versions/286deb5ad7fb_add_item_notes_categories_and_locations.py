"""add item notes, categories and locations

Revision ID: 286deb5ad7fb
Revises: 669fe94b0869
Create Date: 2026-07-02 17:55:09.014239

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '286deb5ad7fb'
down_revision: Union[str, None] = '669fe94b0869'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('items', sa.Column('notes', sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True))

    op.create_table(
        'categories',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('department_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_categories_department_id'), 'categories', ['department_id'], unique=False)

    op.create_table(
        'locations',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('department_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_locations_department_id'), 'locations', ['department_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_locations_department_id'), table_name='locations')
    op.drop_table('locations')
    op.drop_index(op.f('ix_categories_department_id'), table_name='categories')
    op.drop_table('categories')
    op.drop_column('items', 'notes')
