"""custom fields for items

Revision ID: 9f2b6c4d8e1a
Revises: 7a1c9e2f5b3d
Create Date: 2026-07-13 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '9f2b6c4d8e1a'
down_revision: Union[str, None] = '7a1c9e2f5b3d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'custom_field_definitions',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('category_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('field_type', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('options', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('visible_to_all', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['category_id'], ['categories.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_custom_field_definitions_category_id'), 'custom_field_definitions', ['category_id'], unique=False)

    op.create_table(
        'custom_field_values',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('item_id', sa.Uuid(), nullable=False),
        sa.Column('field_id', sa.Uuid(), nullable=False),
        sa.Column('value', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(['item_id'], ['items.id']),
        sa.ForeignKeyConstraint(['field_id'], ['custom_field_definitions.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_custom_field_values_item_id'), 'custom_field_values', ['item_id'], unique=False)
    op.create_index(op.f('ix_custom_field_values_field_id'), 'custom_field_values', ['field_id'], unique=False)
    op.create_unique_constraint(
        'uq_custom_field_values_item_field', 'custom_field_values', ['item_id', 'field_id']
    )


def downgrade() -> None:
    op.drop_constraint('uq_custom_field_values_item_field', 'custom_field_values', type_='unique')
    op.drop_index(op.f('ix_custom_field_values_field_id'), table_name='custom_field_values')
    op.drop_index(op.f('ix_custom_field_values_item_id'), table_name='custom_field_values')
    op.drop_table('custom_field_values')
    op.drop_index(op.f('ix_custom_field_definitions_category_id'), table_name='custom_field_definitions')
    op.drop_table('custom_field_definitions')
