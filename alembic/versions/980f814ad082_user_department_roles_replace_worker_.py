"""user department roles replace worker groups

Revision ID: 980f814ad082
Revises: 2b535eba418c
Create Date: 2026-07-10 03:28:38.806557

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '980f814ad082'
down_revision: Union[str, None] = '2b535eba418c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Neue Tabelle: Rolle pro User UND Abteilung (ersetzt das Gruppen-Konzept)
    op.create_table(
        'user_department_roles',
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('department_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.Enum('ADMIN', 'MITARBEITER', 'NUTZER', name='userrole'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['department_id'], ['departments.id']),
        sa.PrimaryKeyConstraint('user_id', 'department_id'),
    )

    # 2) Datenmigration: bestehende role+department_id auf dem User -> je ein
    # UserDepartmentRole-Eintrag (nichts geht verloren). Admins brauchen keinen
    # Eintrag (globaler Vollzugriff über is_admin).
    op.execute("""
        INSERT INTO user_department_roles (user_id, department_id, role, created_at, updated_at)
        SELECT id, department_id, role, created_at, updated_at
        FROM users
        WHERE role IN ('MITARBEITER', 'NUTZER') AND department_id IS NOT NULL
    """)

    # 3) is_admin-Flag ergänzen und aus der alten role-Spalte befüllen
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE users SET is_admin = true WHERE role = 'ADMIN'")

    # 4) Alte, jetzt überflüssige Spalten/Tabellen entfernen
    with op.batch_alter_table('users') as batch_op:
        batch_op.drop_column('department_id')
        batch_op.drop_column('role')

    with op.batch_alter_table('workers') as batch_op:
        batch_op.drop_constraint('fk_workers_group_id', type_='foreignkey')
        batch_op.drop_column('group_id')

    op.drop_table('group_department_access')
    op.drop_table('worker_groups')


def downgrade() -> None:
    # Bestes-Bemühen-Downgrade: pro User wird (falls vorhanden) EIN
    # UserDepartmentRole-Eintrag zurück auf role+department_id gemappt -
    # falls ein User in mehreren Abteilungen unterschiedliche Rollen hatte,
    # geht diese Differenzierung hier zwangsläufig verloren (das war ja genau
    # der Grund für die Umstellung).
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

    with op.batch_alter_table('users') as batch_op:
        batch_op.add_column(sa.Column('role', sa.Enum('ADMIN', 'MITARBEITER', 'NUTZER', name='userrole'), nullable=True))
        batch_op.add_column(sa.Column('department_id', sa.Uuid(), nullable=True))

    op.execute("UPDATE users SET role = 'ADMIN' WHERE is_admin = true")
    op.execute("""
        UPDATE users SET
            role = COALESCE((SELECT role FROM user_department_roles WHERE user_id = users.id LIMIT 1), 'NUTZER'),
            department_id = (SELECT department_id FROM user_department_roles WHERE user_id = users.id LIMIT 1)
        WHERE is_admin = false
    """)

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column('role', nullable=False)
        batch_op.drop_column('is_admin')

    op.drop_table('user_department_roles')
