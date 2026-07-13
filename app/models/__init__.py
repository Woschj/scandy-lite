"""
Zentraler Import aller Modelle.

Wichtig: SQLModel/Alembic müssen alle Tabellen-Klassen einmal importiert haben,
damit sie in SQLModel.metadata registriert sind (sonst fehlen sie bei create_all
bzw. beim Alembic-Autogenerate). Deshalb hier bündeln statt verstreut importieren.
"""
from app.models.consumable import Consumable, ConsumableUsage  # noqa: F401
from app.models.consumable_reservation import ConsumableReservation  # noqa: F401
from app.models.department import Department  # noqa: F401
from app.models.email_settings import EmailSettings  # noqa: F401
from app.models.item import Item  # noqa: F401
from app.models.lending import Lending  # noqa: F401
from app.models.password_reset_token import PasswordResetToken  # noqa: F401
from app.models.preset import Category, Location  # noqa: F401
from app.models.reservation import Reservation  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.user_department_role import UserDepartmentRole  # noqa: F401
from app.models.worker import Worker  # noqa: F401

__all__ = [
    "Category",
    "Consumable",
    "ConsumableReservation",
    "ConsumableUsage",
    "Department",
    "EmailSettings",
    "Item",
    "Lending",
    "Location",
    "PasswordResetToken",
    "Reservation",
    "User",
    "UserDepartmentRole",
    "Worker",
]
