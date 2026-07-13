"""
Gemeinsame Token-Logik für Passwort-Reset UND die Willkommens-Mail beim
Anlegen eines neuen Kontos (app/routers/auth.py bzw. app/routers/admin_settings.py)
- beide "Passwort selbst festlegen"-Flows brauchen exakt dasselbe: ein
einmalig verwendbares, zeitlich begrenztes Token, keine zweite Token-Art nötig.
"""
import secrets
from datetime import timedelta

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.crypto import hash_token
from app.models.common import utcnow
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User

TOKEN_LIFETIME = timedelta(hours=1)


async def create_reset_token(session: AsyncSession, user: User) -> str:
    raw_token = secrets.token_urlsafe(32)
    session.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(raw_token),
            expires_at=utcnow() + TOKEN_LIFETIME,
        )
    )
    return raw_token


async def resolve_reset_token(session: AsyncSession, raw_token: str) -> PasswordResetToken | None:
    """Gibt den gültigen (nicht abgelaufenen, nicht verbrauchten) Token-
    Datensatz zurück, oder None. Prüft NICHT, ob der zugehörige User noch
    aktiv ist - das macht der Aufrufer, weil sich die Fehlermeldung je nach
    Kontext unterscheidet."""
    result = await session.exec(select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(raw_token)))
    token = result.first()
    if not token or token.used_at is not None or token.expires_at < utcnow():
        return None
    return token


async def invalidate_all_tokens_for_user(session: AsyncSession, user_id) -> None:
    result = await session.exec(
        select(PasswordResetToken).where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
    )
    now = utcnow()
    for token in result.all():
        token.used_at = now
        session.add(token)
