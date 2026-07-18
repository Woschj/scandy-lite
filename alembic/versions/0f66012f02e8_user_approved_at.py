"""user approved_at for SSO account approval gate

Neues Feld auf users: approved_at (NULL = wartet auf Freischaltung durch
einen Admin). Aktuell nur relevant für per SSO/OIDC neu angelegte Konten
(app/routers/oidc.py, JIT-Provisioning) - lokal/per Admin angelegte User
werden mit approved_at gesetzt erzeugt. Getrennt von is_active, weil
is_active auch für "war schon freigeschaltet, wurde aber später deaktiviert"
steht - beide Zustände in einem Feld zu vermischen wäre nicht mehr
unterscheidbar.

Bestehende Zeilen werden auf created_at zurückdatiert (= "waren schon immer
freigeschaltet") - ohne dieses Backfill würden nach dem Deploy plötzlich
ALLE bereits existierenden Benutzer als "wartet auf Freischaltung" auftauchen.

Revision ID: 0f66012f02e8
Revises: c8d3f1a9e0b2
Create Date: 2026-07-18 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0f66012f02e8'
down_revision: Union[str, None] = 'c8d3f1a9e0b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('approved_at', sa.DateTime(), nullable=True))
    op.execute("UPDATE users SET approved_at = created_at WHERE approved_at IS NULL")


def downgrade() -> None:
    op.drop_column('users', 'approved_at')
