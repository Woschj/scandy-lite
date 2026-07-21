"""
Zentrale Konfiguration von Scandy-Lite.
Werte kommen aus Umgebungsvariablen / .env, niemals hartkodiert.
"""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Bekannte, öffentlich in diesem Repo sichtbare Platzhalter (Code-Default hier,
# docker-compose.yml-Fallback) - wer SECRET_KEY vergisst zu setzen, bekommt
# sonst eine App, die nach außen normal funktioniert, aber komplett
# kompromittierbar ist: SECRET_KEY sichert Login-Sessions (JWT), CSRF-Tokens
# UND den Fernet-Schlüssel für verschlüsselt gespeicherte SMTP-Passwörter
# (siehe app/core/crypto.py) - alles drei wäre mit dem bekannten Standardwert
# für jeden nachvollziehbar, der dieses Repo kennt.
_INSECURE_SECRET_KEYS = {"change-me-in-production", "change_me_secret_key", ""}
_MIN_SECRET_KEY_LENGTH = 32  # openssl rand -hex 32 erzeugt 64 Zeichen - großzügige Untergrenze

# Platzhalter aus docker-compose.yml (POSTGRES_PASSWORD-Fallback) - landet bei
# unverändertem .env unverschlüsselt als Teilstring in DATABASE_URL.
_INSECURE_DB_PASSWORD_PLACEHOLDER = "change_me_immediately"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    APP_NAME: str = "Scandy-Lite"
    ENV: str = "development"  # development | production
    SECRET_KEY: str = "change-me-in-production"

    # Datenbank
    DATABASE_URL: str = "postgresql+asyncpg://scandy:scandy@localhost:5432/scandy_lite"
    # Synchrone Variante wird für Alembic-Migrationen benötigt (asyncpg kann Alembic nicht direkt)
    DATABASE_URL_SYNC: str = "postgresql+psycopg2://scandy:scandy@localhost:5432/scandy_lite"

    # Auth (Phase 1: lokal. LDAP/SSO wird später als zusätzlicher auth_source andocken)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12  # 12h, praktisch für Werkstatt-Schichten
    JWT_ALGORITHM: str = "HS256"
    SESSION_COOKIE_NAME: str = "scandy_session"
    # Bewusst NICHT an ENV gekoppelt: "Secure"-Cookies werden von Browsern nur über
    # HTTPS akzeptiert. Läuft die App (wie im internen Netz üblich) über reines HTTP,
    # würde ein Secure-Cookie sonst kommentarlos verworfen -> Login scheint zu "hängen".
    # Erst auf true setzen, wenn ein Reverse-Proxy TLS terminiert.
    SESSION_COOKIE_SECURE: bool = False

    # SSO (optional, via OpenID Connect - z.B. Authentik). Leer = Feature aus,
    # die Login-Seite zeigt dann nur das lokale Formular. Erster Login legt
    # automatisch ein Konto an, aber GESPERRT (approved_at NULL) - ein Admin
    # muss es erst freischalten (Abteilung + Rolle festlegen), siehe
    # app/routers/oidc.py und app/routers/admin_settings.py (pending_accounts).
    OIDC_ISSUER: str = ""
    OIDC_CLIENT_ID: str = ""
    OIDC_CLIENT_SECRET: str = ""
    OIDC_PROVIDER_NAME: str = "SSO"  # Beschriftung des Login-Buttons, z.B. "Authentik"

    # Multi-Abteilung
    DEFAULT_DEPARTMENT_CODE: str = "default"

    # Bild-Uploads (Gegenstände/Verbrauchsmaterial)
    UPLOADS_DIR: str = "uploads"
    MAX_UPLOAD_BYTES: int = 8 * 1024 * 1024  # 8 MB - vor der Pillow-Verarbeitung
    IMAGE_MAX_DIMENSION: int = 900  # px, längere Kante - hält Dateien klein & Karten einheitlich

    @property
    def oidc_enabled(self) -> bool:
        return bool(self.OIDC_ISSUER and self.OIDC_CLIENT_ID and self.OIDC_CLIENT_SECRET)

    @model_validator(mode="after")
    def _require_real_secret_key_in_production(self) -> "Settings":
        """Fail-fast statt still-unsicher: eine vergessene SECRET_KEY in
        Produktion darf nicht zu einer scheinbar normal funktionierenden,
        aber komplett kompromittierbaren App führen (siehe Modul-Kommentar
        oben). In development/Tests bleibt der bequeme Default erlaubt."""
        if self.ENV == "production" and (
            self.SECRET_KEY in _INSECURE_SECRET_KEYS or len(self.SECRET_KEY) < _MIN_SECRET_KEY_LENGTH
        ):
            raise ValueError(
                "SECRET_KEY ist nicht sicher gesetzt (Standardwert oder kürzer als "
                f"{_MIN_SECRET_KEY_LENGTH} Zeichen), ENV=production verlangt aber einen echten Schlüssel. "
                "Erzeugen mit: openssl rand -hex 32 - siehe INSTALL.md."
            )
        return self

    @model_validator(mode="after")
    def _require_real_db_password_in_production(self) -> "Settings":
        """Analog zu SECRET_KEY: der docker-compose.yml-Fallback für
        POSTGRES_PASSWORD ist öffentlich in diesem Repo sichtbar - bleibt er
        in Produktion unverändert, ist die Datenbank für jeden erreichbar,
        der Netzwerkzugriff auf sie hat."""
        if self.ENV == "production" and _INSECURE_DB_PASSWORD_PLACEHOLDER in self.DATABASE_URL:
            raise ValueError(
                "DATABASE_URL enthält noch das unsichere Standard-Passwort "
                f"({_INSECURE_DB_PASSWORD_PLACEHOLDER!r}), ENV=production verlangt aber ein echtes "
                "POSTGRES_PASSWORD. Setzen in der .env - siehe INSTALL.md."
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
