"""
Einmalig verwendbare, zeitlich begrenzte Tokens für den Passwort-Reset- und
Willkommens-Mail-Flow (siehe app/routers/auth.py, app/routers/admin_settings.py).

Es wird bewusst nur der HASH des rohen Tokens gespeichert, nie der Rohwert
selbst - gleiches Prinzip wie beim Session-Cookie: der Server kennt das
Geheimnis nicht im Klartext, nur der Empfänger der E-Mail (siehe
app.core.crypto.hash_token).
"""
import uuid
from datetime import datetime

from sqlmodel import Field

from app.models.common import TimestampMixin, new_uuid


class PasswordResetToken(TimestampMixin, table=True):
    __tablename__ = "password_reset_tokens"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    token_hash: str = Field(index=True, unique=True, max_length=64)
    expires_at: datetime
    used_at: datetime | None = Field(default=None)
