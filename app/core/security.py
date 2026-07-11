"""
Security-Grundbausteine: Passwort-Hashing (lokal) und JWT (Session-Cookie).

Der JWT wird in einem httpOnly-Cookie gespeichert - kein Local-Storage
(XSS-Risiko), kein Bearer-Header-Handling nötig für die HTMX-Seiten.
Gleichzeitig bleibt der Weg offen, dieselben Tokens später auch für eine
mobile App / API-Clients zu nutzen (Authorization-Header funktioniert genauso).
"""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()

_BCRYPT_MAX_BYTES = 72  # bcrypt-Grenze; längere Passwörter werden sauber abgeschnitten statt zu crashen


def hash_password(plain_password: str) -> str:
    pw_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    return bcrypt.hashpw(pw_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    pw_bytes = plain_password.encode("utf-8")[:_BCRYPT_MAX_BYTES]
    try:
        return bcrypt.checkpw(pw_bytes, hashed_password.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(*, subject: str, extra_claims: dict | None = None) -> str:
    """subject = user.id als String. extra_claims z.B. {'role': ..., 'department_id': ...}
    damit spätere Requests die Rolle nicht bei jedem Aufruf neu aus der DB laden müssen."""
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None


def generate_csrf_token(session_value: str) -> str:
    """Stateless CSRF-Token, deterministisch aus dem Session-Cookie-Wert
    abgeleitet (HMAC mit SECRET_KEY) - kein zusätzlicher Server-State nötig.
    Ein Angreifer kann den Wert nicht fälschen, ohne SECRET_KEY zu kennen,
    und kann den httpOnly-Session-Cookie nicht per JS auslesen, um ihn
    selbst abzuleiten."""
    return hmac.new(settings.SECRET_KEY.encode("utf-8"), session_value.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_csrf_token(token: str, session_value: str) -> bool:
    if not token or not session_value:
        return False
    return hmac.compare_digest(token, generate_csrf_token(session_value))
