"""
Mitarbeiterausweis (app.routers.badge, app.routers.admin_settings.user_badge):
QR-Code kodiert denselben Barcode-Wert wie ein normaler Scan-Vorgang, beide
Routen (Selbstbedienung + Admin-Ansicht für einen beliebigen Benutzer) nutzen
dasselbe Template.
"""
import uuid

import pytest_asyncio

from app.core.security import hash_password
from app.models.user import User
from tests.conftest import STAFF_PASSWORD, STAFF_USERNAME, login


@pytest_asyncio.fixture
async def admin_client(client, session_maker):
    async with session_maker() as session:
        admin = User(username="admin", is_admin=True, hashed_password=hash_password("adminpass123"))
        session.add(admin)
        await session.commit()
    await login(client, "admin", "adminpass123")
    return client


async def test_my_badge_shows_qr_for_user_with_barcode(client, seed_data):
    await login(client, STAFF_USERNAME, STAFF_PASSWORD)
    resp = await client.get("/me/ausweis")
    assert resp.status_code == 200
    assert "data:image/png;base64," in resp.text
    assert "W-STAFF" in resp.text  # seed_data-Barcode, siehe tests/conftest.py


async def test_my_badge_shows_hint_when_no_barcode(client, session_maker):
    async with session_maker() as session:
        user = User(username="no-badge", hashed_password=hash_password("pass12345"))
        session.add(user)
        await session.commit()
    await login(client, "no-badge", "pass12345")
    resp = await client.get("/me/ausweis")
    assert resp.status_code == 200
    assert "data:image/png;base64," not in resp.text
    assert "noch kein Ausweis-Barcode hinterlegt" in resp.text


async def test_my_badge_requires_login(client):
    resp = await client.get("/me/ausweis", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


async def test_admin_can_view_any_users_badge(admin_client, session_maker, seed_data):
    async with session_maker() as session:
        worker = User(
            username="worker-x", barcode="WORKER-X", first_name="Worker", last_name="X",
            department_id=seed_data["department_id"],
        )
        session.add(worker)
        await session.commit()
        await session.refresh(worker)
        worker_id = worker.id

    resp = await admin_client.get(f"/admin/users/{worker_id}/ausweis")
    assert resp.status_code == 200
    assert "data:image/png;base64," in resp.text
    assert "WORKER-X" in resp.text


async def test_non_admin_cannot_view_other_users_badge(client, seed_data):
    """require_admin blockt vor dem Nachschlagen - die konkrete user_id im
    Pfad ist deshalb für diesen Test irrelevant, solange sie ein gueltiges
    UUID-Format hat."""
    await login(client, STAFF_USERNAME, STAFF_PASSWORD)
    resp = await client.get(f"/admin/users/{uuid.uuid4()}/ausweis", follow_redirects=False)
    assert resp.status_code == 403


async def test_admin_badge_unknown_user_redirects_to_users_tab(admin_client):
    resp = await admin_client.get(f"/admin/users/{uuid.uuid4()}/ausweis", follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/settings#users"
