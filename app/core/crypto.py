"""
Verschlüsselung für "at rest" gespeicherte Geheimnisse, die (anders als
Passwörter) wieder im Klartext gebraucht werden - aktuell nur das SMTP-
Passwort in EmailSettings (siehe app/models/email_settings.py).

Der Fernet-Schlüssel wird deterministisch aus SECRET_KEY abgeleitet (kein
zusätzlicher Server-State, kein zweites Geheimnis zu verwalten) - gleiches
Prinzip wie generate_csrf_token in app/core/security.py. cryptography ist
bereits transitiv über python-jose[cryptography] installiert.
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings

settings = get_settings()


def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest())
    return Fernet(key)


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode("utf-8")).decode("utf-8")


def decrypt_secret(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return None


def hash_token(raw_token: str) -> str:
    """Für Passwort-Reset-Tokens (siehe app.models.password_reset_token):
    simpler SHA-256-Hash reicht hier aus (kein Passwort, sondern ein
    hochentropisches secrets.token_urlsafe(32) - kein Bruteforce-Risiko wie
    bei bcrypt-pflichtigen Nutzerpasswörtern)."""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
