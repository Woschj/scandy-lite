"""
Gemeinsame Test-Fixtures: frische SQLite-DB pro Test (aiosqlite,
PRAGMA foreign_keys=ON - siehe PROJECT_STATUS_FOR_CLAUDE_CODE.md Abschnitt 7:
SQLite prüft Fremdschlüssel standardmäßig NICHT, das hat in der Vergangenheit
reale Postgres-Bugs verdeckt), plus ein httpx.AsyncClient gegen die echte
FastAPI-App (app.core.database.get_session wird per dependency_overrides auf
die Test-Engine umgebogen).
"""
import app.models  # noqa: F401  (registriert alle Tabellen in SQLModel.metadata)
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import database as db_module
from app.core.config import get_settings
from app.core.security import generate_csrf_token, hash_password
from app.main import app
from app.models.common import UserRole
from app.models.department import Department
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole
from app.models.worker import Worker

STAFF_USERNAME = "staff"
STAFF_PASSWORD = "staffpass123"


@pytest_asyncio.fixture
async def engine():
    test_engine = create_async_engine("sqlite+aiosqlite://")

    @event.listens_for(test_engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with test_engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield test_engine
    await test_engine.dispose()


@pytest_asyncio.fixture
async def session_maker(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def seed_data(session_maker):
    """Eine Abteilung + ein Mitarbeiter-Login (mit verknüpftem Worker-Ausweis),
    das in dieser Abteilung die Mitarbeiter-Rolle hat - deckt die meisten
    mutierenden Routen ab (require_staff + is_staff_in_department)."""
    async with session_maker() as session:
        department = Department(code="werkstatt", name="Werkstatt")
        session.add(department)
        await session.commit()
        await session.refresh(department)

        staff_user = User(username=STAFF_USERNAME, is_admin=False, hashed_password=hash_password(STAFF_PASSWORD))
        session.add(staff_user)
        await session.commit()
        await session.refresh(staff_user)

        session.add(UserDepartmentRole(user_id=staff_user.id, department_id=department.id, role=UserRole.MITARBEITER))
        session.add(Worker(barcode="W-STAFF", first_name="Staff", last_name="Worker", department_id=department.id, user_id=staff_user.id))
        await session.commit()

        return {
            "department_id": department.id,
            "staff_username": STAFF_USERNAME,
            "staff_password": STAFF_PASSWORD,
        }


@pytest_asyncio.fixture
async def client(session_maker):
    async def _get_session_override():
        async with session_maker() as session:
            yield session

    app.dependency_overrides[db_module.get_session] = _get_session_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def login(client: AsyncClient, username: str, password: str) -> None:
    resp = await client.post("/auth/login", data={"username": username, "password": password})
    assert resp.status_code == 303, resp.text


def csrf_value(client: AsyncClient) -> str:
    """Token passend zum aktuell im Client gespeicherten Session-Cookie -
    simuliert das versteckte Formularfeld, das echte Templates über
    `{{ csrf_token(request) }}` rendern (siehe app/core/templating.py)."""
    settings = get_settings()
    session_cookie = client.cookies.get(settings.SESSION_COOKIE_NAME)
    assert session_cookie, "Kein Session-Cookie gesetzt - vorher login() aufrufen."
    return generate_csrf_token(session_cookie)
