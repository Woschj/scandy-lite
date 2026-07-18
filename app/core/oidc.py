"""
Optionales SSO-Login via OpenID Connect (siehe app/routers/oidc.py) - z.B.
gegen einen selbst gehosteten Authentik-Server, funktioniert aber mit jedem
Standard-OIDC-Provider. Bewusst Authlib statt eigener Token-/JWKS-
Verifikation: Signatur/aud/iss/exp-Prüfung selbst zu bauen ist genau die Art
sicherheitskritischer Code, bei der ein eigener Fehler teuer wird.

oauth.oidc ist nur registriert, wenn settings.oidc_enabled ist (leere
Provider-Config -> kein Registrierungsversuch, der sonst beim App-Start an
der fehlenden server_metadata_url scheitern würde).
"""
import re
import uuid

from authlib.integrations.starlette_client import OAuth
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings
from app.models.user import User

settings = get_settings()

oauth = OAuth()
if settings.oidc_enabled:
    oauth.register(
        name="oidc",
        server_metadata_url=f"{settings.OIDC_ISSUER.rstrip('/')}/.well-known/openid-configuration",
        client_id=settings.OIDC_CLIENT_ID,
        client_secret=settings.OIDC_CLIENT_SECRET,
        client_kwargs={"scope": "openid email profile"},
    )

_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]")


async def unique_username_from_claims(session: AsyncSession, claims: dict, sub: str) -> str:
    """Erster Login einer Person via SSO: Scandy-Lite braucht einen eigenen,
    eindeutigen Benutzernamen, den der Provider uns nicht zwingend in dieser
    Form liefert. Reihenfolge: preferred_username -> E-Mail-Lokalteil -> ein
    Teil der Subject-ID, mit Zahlen-Suffix bis ein freier Name gefunden ist.
    Der Nutzer tippt diesen Namen nie selbst ein (SSO), er muss nur intern
    eindeutig und stabil sein."""
    candidates = []
    preferred = claims.get("preferred_username")
    if preferred:
        candidates.append(_SLUG_RE.sub("", preferred).lower())
    email = claims.get("email")
    if email and "@" in email:
        candidates.append(_SLUG_RE.sub("", email.split("@")[0]).lower())
    candidates.append(f"sso-{sub[:8]}")

    for base in candidates:
        if not base:
            continue
        for suffix in range(20):
            candidate = base if suffix == 0 else f"{base}{suffix}"
            existing = await session.exec(select(User).where(User.username == candidate))
            if not existing.first():
                return candidate

    return f"sso-{uuid.uuid4().hex[:12]}"
