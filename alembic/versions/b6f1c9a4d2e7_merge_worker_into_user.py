"""merge worker into user

User und Worker werden zu einer Entität: jeder, der ausleiht, ist jetzt ein
User (Login optional - `hashed_password` bleibt NULL für reine Ausweis-
Inhaber ohne Login, genau wie bisher ein Worker ohne user_id). Der separate
`/workers`-Bereich und das Worker-Modell entfallen.

Vorgehen:
1. users bekommt die bisherigen Worker-Spalten (first_name, last_name,
   barcode, department_id, deleted_at), alle nullable.
2. Für Worker MIT Login: Felder auf den verknüpften User kopieren.
3. Für Worker OHNE Login: neuer User-Row - WICHTIG: bekommt bewusst dieselbe
   id wie der alte Worker, damit die vier Historien-Tabellen (lendings,
   reservations, consumable_usages, consumable_reservations) ihre
   worker_id-Werte NICHT umschreiben müssen, wenn sie später auf users statt
   workers zeigen.
4. Alte FK-Constraints der vier Tabellen (zeigen noch auf workers.id) lösen
   (per pg_constraint-Introspektion, nicht per hartcodiertem Namen - robust
   gegenüber abweichender Auto-Benennung) - MUSS vor Schritt 5 passieren,
   sonst lehnt Postgres jeden worker_id-Wert ab, der nur in users existiert.
5. Für Worker MIT Login: worker_id in den vier Historien-Tabellen auf
   worker.user_id ummappen (dort weichen alte Worker-id und User-id ja
   voneinander ab).
6. Neue FK-Constraints der vier Tabellen auf users.id anlegen.
7. Barcode-Eindeutigkeit (partieller Unique-Index wie bisher bei workers,
   siehe Migration 45dd75eab85a) auf users verschieben.
8. workers-Tabelle droppen (nimmt ihre eigenen Indizes/Constraints mit).

Revision ID: b6f1c9a4d2e7
Revises: 5e8a2c1f9b6d
Create Date: 2026-07-14 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = 'b6f1c9a4d2e7'
down_revision: Union[str, None] = '5e8a2c1f9b6d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HISTORY_TABLES = ("lendings", "reservations", "consumable_usages", "consumable_reservations")


def upgrade() -> None:
    # 1. Neue Spalten auf users
    op.add_column('users', sa.Column('first_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True))
    op.add_column('users', sa.Column('last_name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True))
    op.add_column('users', sa.Column('barcode', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True))
    op.add_column('users', sa.Column('department_id', sa.Uuid(), nullable=True))
    op.add_column('users', sa.Column('deleted_at', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_users_barcode'), 'users', ['barcode'], unique=False)
    op.create_index(op.f('ix_users_department_id'), 'users', ['department_id'], unique=False)
    op.create_foreign_key('fk_users_department_id', 'users', 'departments', ['department_id'], ['id'])

    # 2. Worker MIT Login: Felder auf den verknüpften User übernehmen
    op.execute(
        "UPDATE users SET "
        "first_name = workers.first_name, "
        "last_name = workers.last_name, "
        "barcode = workers.barcode, "
        "department_id = workers.department_id, "
        "deleted_at = workers.deleted_at, "
        "is_active = (users.is_active AND workers.is_active) "
        "FROM workers WHERE workers.user_id = users.id"
    )

    # 3. Worker OHNE Login: neuer User mit IDENTISCHER id wie der alte Worker
    # (siehe Modul-Docstring) - dadurch bleiben Fremdschlüssel in den
    # Historien-Tabellen fuer diese Faelle automatisch korrekt.
    # 'LOCAL' (nicht 'local'): Postgres-Enums aus sa.Enum(PythonEnum) speichern
    # per Default den MEMBER-NAMEN (AuthSource.LOCAL.name), nicht den Wert
    # (AuthSource.LOCAL.value == "local") - siehe initiale Migration
    # 66ba7c1819b7 (sa.Enum('LOCAL', 'LDAP', 'SSO', name='authsource')).
    op.execute(
        "INSERT INTO users "
        "(id, created_at, updated_at, username, email, is_admin, auth_source, "
        " hashed_password, external_id, is_active, first_name, last_name, barcode, department_id, deleted_at) "
        "SELECT w.id, w.created_at, w.updated_at, "
        "       'mitarbeiter-' || lower(regexp_replace(w.barcode, '[^a-zA-Z0-9]+', '-', 'g')) || '-' || substr(w.id::text, 1, 8), "
        "       NULL, false, 'LOCAL', NULL, NULL, w.is_active, "
        "       w.first_name, w.last_name, w.barcode, w.department_id, w.deleted_at "
        "FROM workers w WHERE w.user_id IS NULL"
    )

    # 4. FK-Constraints der Historien-Tabellen von workers loesen (per
    # Introspektion statt hartcodiertem Namen - robust gegenueber
    # abweichender Auto-Benennung durch Postgres) - MUSS vor dem Ummappen in
    # Schritt 5 passieren: solange die alte FK noch auf workers.id zeigt,
    # verweigert Postgres jeden worker_id-Wert, der nur in users existiert
    # (z.B. der neuen user_id eines verknuepften Workers).
    for table in _HISTORY_TABLES:
        op.execute(f"""
            DO $$
            DECLARE
                r RECORD;
            BEGIN
                FOR r IN
                    SELECT conname FROM pg_constraint
                    WHERE contype = 'f' AND conrelid = '{table}'::regclass AND confrelid = 'workers'::regclass
                LOOP
                    EXECUTE format('ALTER TABLE {table} DROP CONSTRAINT %I', r.conname);
                END LOOP;
            END $$;
        """)

    # 5. Worker MIT Login: worker_id in den Historien-Tabellen auf die
    # tatsaechliche User-id ummappen (weicht hier von worker.id ab).
    for table in _HISTORY_TABLES:
        op.execute(
            f"UPDATE {table} t SET worker_id = w.user_id "
            f"FROM workers w WHERE t.worker_id = w.id AND w.user_id IS NOT NULL"
        )

    # 6. Neue FK-Constraints der Historien-Tabellen auf users anlegen.
    for table in _HISTORY_TABLES:
        op.create_foreign_key(f'fk_{table}_worker_id_users', table, 'users', ['worker_id'], ['id'])

    # 7. Barcode-Eindeutigkeit (nur aktive Datensaetze) auf users verschieben
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_barcode_active "
        "ON users (barcode) WHERE deleted_at IS NULL"
    )

    # 8. workers-Tabelle droppen (nimmt ihre eigenen Indizes/Constraints mit)
    op.drop_table('workers')


def downgrade() -> None:
    raise NotImplementedError(
        "Downgrade fuer den Worker/User-Merge ist nicht unterstuetzt - die "
        "Trennung in zwei Tabellen liesse sich aus den zusammengefuehrten "
        "Daten nicht mehr verlustfrei rekonstruieren (z.B. welche User vorher "
        "ueberhaupt einen Worker hatten). Vor dem Upgrade ein DB-Backup ziehen."
    )
