"""
Datenbank-Layer: async SQLModel-Engine + Session-Dependency für FastAPI.

Hinweis: Für Alembic-Migrationen wird separat eine synchrone Engine verwendet
(siehe alembic/env.py), da Alembic (noch) nicht sauber async arbeitet.
"""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    echo=(settings.ENV == "development"),
    pool_pre_ping=True,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI-Dependency: liefert eine DB-Session pro Request."""
    async with async_session_maker() as session:
        yield session


async def init_db() -> None:
    """Nur für lokale Entwicklung/Tests - Produktiv-Schema kommt über Alembic-Migrationen."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
