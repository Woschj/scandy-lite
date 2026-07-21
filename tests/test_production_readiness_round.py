"""Regressionstests für die Production-Readiness-Runde: /health mit echtem
DB-Check, Pagination für Gegenstände/Verbrauchsmaterial-Listen (analog zu den
history.py-Page-Tests), POSTGRES_PASSWORD-Fail-Fast (siehe test_config_security.py).
"""
import uuid

import pytest_asyncio

from app.models.consumable import Consumable
from app.models.item import Item
from tests.conftest import login


@pytest_asyncio.fixture
async def staff_client(client, seed_data):
    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    return client


async def test_health_ok_when_db_reachable(client, engine, monkeypatch):
    # /health prüft direkt über die globale `engine` (app/core/database.py),
    # nicht über die per get_session überschriebene Test-Session - deshalb
    # hier zusätzlich die Test-Engine unterschieben (sonst würde /health
    # gegen die echte, im Test nicht erreichbare Produktions-DATABASE_URL laufen).
    import app.main as main_module
    monkeypatch.setattr(main_module, "engine", engine)

    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_health_returns_503_when_db_unreachable(client, monkeypatch):
    import app.main as main_module

    class _BrokenEngine:
        def connect(self):
            raise ConnectionError("DB nicht erreichbar (simuliert)")

    monkeypatch.setattr(main_module, "engine", _BrokenEngine())
    resp = await client.get("/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "error"


async def test_items_list_page_zero_does_not_break(staff_client):
    resp = await staff_client.get("/items?page=0")
    assert resp.status_code == 200


async def test_items_list_negative_page_does_not_break(staff_client):
    resp = await staff_client.get("/items?page=-3")
    assert resp.status_code == 200


async def test_items_list_pagination_has_more(staff_client, session_maker, seed_data):
    async with session_maker() as session:
        for i in range(65):
            session.add(Item(barcode=f"PAGE-ITEM-{i}-{uuid.uuid4().hex[:6]}", name=f"Item {i}", department_id=seed_data["department_id"]))
        await session.commit()

    resp = await staff_client.get("/items")
    assert resp.status_code == 200
    assert "Weiter" in resp.text

    resp_page2 = await staff_client.get("/items?page=2")
    assert resp_page2.status_code == 200


async def test_consumables_list_pagination_has_more(staff_client, session_maker, seed_data):
    async with session_maker() as session:
        for i in range(65):
            session.add(Consumable(barcode=f"PAGE-CONS-{i}-{uuid.uuid4().hex[:6]}", name=f"Material {i}", department_id=seed_data["department_id"]))
        await session.commit()

    resp = await staff_client.get("/consumables")
    assert resp.status_code == 200
    assert "Weiter" in resp.text

    resp_page2 = await staff_client.get("/consumables?page=2")
    assert resp_page2.status_code == 200
