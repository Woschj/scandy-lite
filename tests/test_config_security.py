"""
Regressionstest für den Fail-Fast-Check in app.core.config: eine vergessene
SECRET_KEY darf in Produktion nicht zu einer scheinbar normal
funktionierenden, aber komplett kompromittierbaren App führen (JWT-Sessions,
CSRF-Tokens und die verschlüsselten SMTP-Passwörter hängen alle daran).
"""
import pytest

from app.core.config import Settings


def test_production_with_default_secret_key_raises():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ENV="production", SECRET_KEY="change-me-in-production")


def test_production_with_compose_default_secret_key_raises():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ENV="production", SECRET_KEY="change_me_secret_key")


def test_production_with_too_short_secret_key_raises():
    with pytest.raises(ValueError, match="SECRET_KEY"):
        Settings(ENV="production", SECRET_KEY="zu-kurz")


def test_production_with_proper_secret_key_succeeds():
    settings = Settings(ENV="production", SECRET_KEY="a" * 64)
    assert settings.SECRET_KEY == "a" * 64


def test_development_with_default_secret_key_does_not_raise():
    settings = Settings(ENV="development", SECRET_KEY="change-me-in-production")
    assert settings.ENV == "development"


def test_production_with_compose_default_db_password_raises():
    with pytest.raises(ValueError, match="DATABASE_URL"):
        Settings(
            ENV="production",
            SECRET_KEY="a" * 64,
            DATABASE_URL="postgresql+asyncpg://scandy:change_me_immediately@db:5432/scandy_lite",
        )


def test_production_with_proper_db_password_succeeds():
    settings = Settings(
        ENV="production",
        SECRET_KEY="a" * 64,
        DATABASE_URL="postgresql+asyncpg://scandy:a-real-password@db:5432/scandy_lite",
    )
    assert "change_me_immediately" not in settings.DATABASE_URL


def test_development_with_placeholder_db_password_does_not_raise():
    settings = Settings(
        ENV="development",
        SECRET_KEY="change-me-in-production",
        DATABASE_URL="postgresql+asyncpg://scandy:change_me_immediately@db:5432/scandy_lite",
    )
    assert settings.ENV == "development"
