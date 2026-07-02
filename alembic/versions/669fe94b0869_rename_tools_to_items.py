"""rename tools to items

Revision ID: 669fe94b0869
Revises: 66ba7c1819b7
Create Date: 2026-07-02 17:37:41.956576

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = '669fe94b0869'
down_revision: Union[str, None] = '66ba7c1819b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Begrifflichkeit "Werkzeug" -> neutral "Gegenstand" (Item), da nicht jede
    # Abteilung zwingend Werkzeuge im engeren Sinn ausleiht.
    op.rename_table("tools", "items")
    op.alter_column("lendings", "tool_id", new_column_name="item_id")

    # Der Foreign-Key- und Index-Name bleibt technisch funktionsfähig, auch wenn
    # er noch "tool" im Namen trägt - kosmetisch aber sauberer, ihn mit umzubenennen.
    op.execute("ALTER INDEX IF EXISTS ix_tools_barcode RENAME TO ix_items_barcode")
    op.execute("ALTER INDEX IF EXISTS ix_tools_department_id RENAME TO ix_items_department_id")
    op.execute("ALTER INDEX IF EXISTS ix_lendings_tool_id RENAME TO ix_lendings_item_id")

    # Postgres legt für Python-Enums einen eigenen benannten Typ an - der muss mit umbenannt werden.
    op.execute("ALTER TYPE toolstatus RENAME TO itemstatus")


def downgrade() -> None:
    op.execute("ALTER TYPE itemstatus RENAME TO toolstatus")

    op.execute("ALTER INDEX IF EXISTS ix_items_barcode RENAME TO ix_tools_barcode")
    op.execute("ALTER INDEX IF EXISTS ix_items_department_id RENAME TO ix_tools_department_id")
    op.execute("ALTER INDEX IF EXISTS ix_lendings_item_id RENAME TO ix_lendings_tool_id")

    op.alter_column("lendings", "item_id", new_column_name="tool_id")
    op.rename_table("items", "tools")
