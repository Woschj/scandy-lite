"""fix custom_field_definitions.field_type to use a native enum type

Die vorherige Migration (9f2b6c4d8e1a) hat field_type faelschlich als
VARCHAR angelegt - das SQLModel-Feld ist aber ein (str, Enum)-Typ
(CustomFieldType), fuer den SQLAlchemy beim INSERT/SELECT einen nativen
Postgres-ENUM-Typ erwartet (genau wie bei ItemStatus/UserRole, siehe
alembic/versions/66ba7c1819b7_..., dort 'toolstatus'/'userrole'). Ohne
diesen Typ schlaegt jedes INSERT mit
"type "customfieldtype" does not exist" fehl.

Revision ID: 3d7e5a1c9f04
Revises: 9f2b6c4d8e1a
Create Date: 2026-07-13 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3d7e5a1c9f04'
down_revision: Union[str, None] = '9f2b6c4d8e1a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

customfieldtype_enum = postgresql.ENUM('TEXT', 'NUMBER', 'DATE', 'SELECT', name='customfieldtype')


def upgrade() -> None:
    customfieldtype_enum.create(op.get_bind(), checkfirst=True)
    op.alter_column(
        'custom_field_definitions', 'field_type',
        existing_type=sa.String(),
        type_=customfieldtype_enum,
        postgresql_using='field_type::customfieldtype',
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        'custom_field_definitions', 'field_type',
        existing_type=customfieldtype_enum,
        type_=sa.String(),
        postgresql_using='field_type::text',
        existing_nullable=False,
    )
    customfieldtype_enum.drop(op.get_bind(), checkfirst=True)
