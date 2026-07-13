"""
System-Mail-Versand (Passwort-Reset, Willkommens-Mail). SMTP-Zugangsdaten
kommen aus der EmailSettings-Singleton-Zeile (Einstellungen -> E-Mail),
nicht aus Umgebungsvariablen - siehe app/models/email_settings.py.

WICHTIG: send_email() wirft nie. Ein SMTP-Fehler (falsche Zugangsdaten,
Server nicht erreichbar, ...) darf niemals einen Kern-Workflow wie das
Anlegen eines Benutzers zum Scheitern bringen - der Aufrufer bekommt nur
False zurück und kann optional eine Warnung anzeigen.
"""
import logging
import smtplib
from email.message import EmailMessage

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.crypto import decrypt_secret
from app.models.email_settings import EmailSettings

logger = logging.getLogger("scandy.email")


async def get_email_settings(session: AsyncSession) -> EmailSettings | None:
    result = await session.exec(select(EmailSettings).limit(1))
    return result.first()


def _send_sync(settings: EmailSettings, to_addr: str, subject: str, html_body: str) -> None:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f"{settings.from_name} <{settings.from_address}>"
    message["To"] = to_addr
    message.set_content("Diese E-Mail benötigt einen HTML-fähigen E-Mail-Client.")
    message.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.use_tls:
            smtp.starttls()
        if settings.smtp_username:
            password = decrypt_secret(settings.smtp_password_encrypted or "") or ""
            smtp.login(settings.smtp_username, password)
        smtp.send_message(message)


async def send_email(session: AsyncSession, to_addr: str, subject: str, html_body: str) -> bool:
    settings = await get_email_settings(session)
    if not settings or not settings.enabled:
        logger.warning("E-Mail-Versand übersprungen (nicht konfiguriert/aktiviert): %s", subject)
        return False

    try:
        await run_in_threadpool(_send_sync, settings, to_addr, subject, html_body)
        return True
    except Exception:
        logger.exception("E-Mail-Versand fehlgeschlagen: %s -> %s", subject, to_addr)
        return False
