"""nullable FKs + name snapshots for lendings/reservations/consumable_usages/consumable_reservations

Ermöglicht den Papierkorb (app/core/trash.py): ein Gegenstand/Verbrauchs-
material/Mitarbeiter kann endgültig gelöscht werden, ohne die Historie zu
zerreißen - die FK-Spalte wird auf NULL gesetzt, Name/Barcode bleiben als
Text-Schnappschuss in der jeweiligen Historien-Zeile erhalten.

Revision ID: 5e8a2c1f9b6d
Revises: 3d7e5a1c9f04
Create Date: 2026-07-13 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '5e8a2c1f9b6d'
down_revision: Union[str, None] = '3d7e5a1c9f04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column('lendings', 'item_id', existing_type=sa.Uuid(), nullable=True)
    op.alter_column('lendings', 'worker_id', existing_type=sa.Uuid(), nullable=True)
    op.add_column('lendings', sa.Column('item_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))
    op.add_column('lendings', sa.Column('item_barcode_snapshot', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True))
    op.add_column('lendings', sa.Column('worker_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))

    op.alter_column('reservations', 'item_id', existing_type=sa.Uuid(), nullable=True)
    op.alter_column('reservations', 'worker_id', existing_type=sa.Uuid(), nullable=True)
    op.add_column('reservations', sa.Column('item_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))
    op.add_column('reservations', sa.Column('item_barcode_snapshot', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True))
    op.add_column('reservations', sa.Column('worker_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))

    op.alter_column('consumable_usages', 'consumable_id', existing_type=sa.Uuid(), nullable=True)
    op.alter_column('consumable_usages', 'worker_id', existing_type=sa.Uuid(), nullable=True)
    op.add_column('consumable_usages', sa.Column('consumable_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))
    op.add_column('consumable_usages', sa.Column('worker_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))
    # Denormalisiertes department_id (wie schon bei lendings vorhanden) -
    # die Abteilungs-Sichtbarkeit in der Historie darf nicht vom (nach einem
    # Papierkorb-Purge ggf. NULL gewordenen) consumable_id abhängen. Erst
    # nullable anlegen + aus der (noch existierenden) Consumable-Beziehung
    # zurückfüllen, dann NOT NULL erzwingen.
    op.add_column('consumable_usages', sa.Column('department_id', sa.Uuid(), nullable=True))
    op.execute(
        "UPDATE consumable_usages SET department_id = consumables.department_id "
        "FROM consumables WHERE consumables.id = consumable_usages.consumable_id"
    )
    op.alter_column('consumable_usages', 'department_id', existing_type=sa.Uuid(), nullable=False)
    op.create_foreign_key('fk_consumable_usages_department_id', 'consumable_usages', 'departments', ['department_id'], ['id'])
    op.create_index(op.f('ix_consumable_usages_department_id'), 'consumable_usages', ['department_id'], unique=False)

    op.alter_column('consumable_reservations', 'consumable_id', existing_type=sa.Uuid(), nullable=True)
    op.alter_column('consumable_reservations', 'worker_id', existing_type=sa.Uuid(), nullable=True)
    op.add_column('consumable_reservations', sa.Column('consumable_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))
    op.add_column('consumable_reservations', sa.Column('consumable_barcode_snapshot', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True))
    op.add_column('consumable_reservations', sa.Column('worker_name_snapshot', sqlmodel.sql.sqltypes.AutoString(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('consumable_reservations', 'worker_name_snapshot')
    op.drop_column('consumable_reservations', 'consumable_barcode_snapshot')
    op.drop_column('consumable_reservations', 'consumable_name_snapshot')
    op.alter_column('consumable_reservations', 'worker_id', existing_type=sa.Uuid(), nullable=False)
    op.alter_column('consumable_reservations', 'consumable_id', existing_type=sa.Uuid(), nullable=False)

    op.drop_index(op.f('ix_consumable_usages_department_id'), table_name='consumable_usages')
    op.drop_constraint('fk_consumable_usages_department_id', 'consumable_usages', type_='foreignkey')
    op.drop_column('consumable_usages', 'department_id')
    op.drop_column('consumable_usages', 'worker_name_snapshot')
    op.drop_column('consumable_usages', 'consumable_name_snapshot')
    op.alter_column('consumable_usages', 'worker_id', existing_type=sa.Uuid(), nullable=False)
    op.alter_column('consumable_usages', 'consumable_id', existing_type=sa.Uuid(), nullable=False)

    op.drop_column('reservations', 'worker_name_snapshot')
    op.drop_column('reservations', 'item_barcode_snapshot')
    op.drop_column('reservations', 'item_name_snapshot')
    op.alter_column('reservations', 'worker_id', existing_type=sa.Uuid(), nullable=False)
    op.alter_column('reservations', 'item_id', existing_type=sa.Uuid(), nullable=False)

    op.drop_column('lendings', 'worker_name_snapshot')
    op.drop_column('lendings', 'item_barcode_snapshot')
    op.drop_column('lendings', 'item_name_snapshot')
    op.alter_column('lendings', 'worker_id', existing_type=sa.Uuid(), nullable=False)
    op.alter_column('lendings', 'item_id', existing_type=sa.Uuid(), nullable=False)
