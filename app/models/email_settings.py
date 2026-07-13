"""
SMTP-Zugangsdaten für den System-Mail-Versand (Passwort-Reset, Willkommens-
Mail). Singleton-Tabelle - es existiert immer höchstens eine Zeile, gepflegt
über Einstellungen -> E-Mail (siehe app/routers/admin_settings.py).

Das Passwort steht nie im Klartext in der DB (siehe app/core/crypto.py).
"""
import uuid

from sqlmodel import Field

from app.models.common import TimestampMixin, new_uuid


class EmailSettings(TimestampMixin, table=True):
    __tablename__ = "email_settings"

    id: uuid.UUID = Field(default_factory=new_uuid, primary_key=True)

    smtp_host: str = Field(max_length=255)
    smtp_port: int = Field(default=587)
    smtp_username: str | None = Field(default=None, max_length=255)
    smtp_password_encrypted: str | None = Field(default=None)
    use_tls: bool = Field(default=True)

    from_address: str = Field(max_length=255)
    from_name: str = Field(default="Scandy-Lite", max_length=255)

    # Erst nach explizitem Admin-Häkchen aktiv - verhindert, dass ein
    # halb ausgefülltes Formular (z.B. Test während der Eingabe) versehentlich
    # schon "scharf" ist und beim nächsten User-Anlegen eine Mail verschickt.
    enabled: bool = Field(default=False)
