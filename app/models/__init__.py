"""
Zentraler Import aller Modelle.

Wichtig: SQLModel/Alembic müssen alle Tabellen-Klassen einmal importiert haben,
damit sie in SQLModel.metadata registriert sind (sonst fehlen sie bei create_all
bzw. beim Alembic-Autogenerate). Deshalb hier bündeln statt verstreut importieren.
"""
from app.models.consumable import Consumable, ConsumableUsage  # noqa: F401
from app.models.department import Department  # noqa: F401
from app.models.lending import Lending  # noqa: F401
from app.models.tool import Tool  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.worker import Worker  # noqa: F401

__all__ = [
    "Consumable",
    "ConsumableUsage",
    "Department",
    "Lending",
    "Tool",
    "User",
    "Worker",
]
