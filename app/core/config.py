"""
Zentrale Konfiguration von Scandy-Lite.
Werte kommen aus Umgebungsvariablen / .env, niemals hartkodiert.
"""
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # Multi-Abteilung
    DEFAULT_DEPARTMENT_CODE: str = "default"


@lru_cache
def get_settings() -> Settings:
    return Settings()
