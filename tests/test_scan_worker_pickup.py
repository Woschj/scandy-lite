"""
Regressionstest für app.routers.scan.scan_lookup: Scannen des Mitarbeiter-
Ausweis-Barcodes (statt Gegenstand/Verbrauchsmaterial) leitet bei offener(n)
Reservierung(en) direkt zur Sammel-Ausgabe weiter (app.routers.pickup),
ohne offene Reservierung gibt es stattdessen einen kurzen Hinweis statt
fälschlich "nicht gefunden".
"""
import pytest_asyncio

from app.models.item import Item
from app.models.reservation import Reservation
from app.models.user import User
from tests.conftest import csrf_value, login


@pytest_asyncio.fixture
async def staff_client(client, seed_data):
    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    return client


async def test_scan_worker_barcode_with_open_reservation_redirects_to_pickup(staff_client, session_maker, seed_data):
    async with session_maker() as session:
        item = Item(barcode="ITEM-PICKUP-1", name="Akkuschrauber", department_id=seed_data["department_id"])
        worker = User(
            username="picker-scan-1", barcode="W-PICKER-SCAN-1", first_name="Erika", last_name="Muster",
            department_id=seed_data["department_id"],
        )
        session.add(item)
        session.add(worker)
        await session.commit()
        await session.refresh(item)
        await session.refresh(worker)

        session.add(Reservation(item_id=item.id, worker_id=worker.id, department_id=seed_data["department_id"]))
        await session.commit()
        worker_id = worker.id

    resp = await staff_client.post(
        "/scan/lookup",
        data={"barcode": "W-PICKER-SCAN-1", "csrf_token": csrf_value(staff_client)},
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/scan/pickup/{worker_id}"


async def test_scan_worker_barcode_without_reservation_shows_hint(staff_client, session_maker, seed_data):
    async with session_maker() as session:
        worker = User(
            username="picker-scan-2", barcode="W-PICKER-SCAN-2", first_name="Max", last_name="Ohne-Reservierung",
            department_id=seed_data["department_id"],
        )
        session.add(worker)
        await session.commit()

    resp = await staff_client.post(
        "/scan/lookup",
        data={"barcode": "W-PICKER-SCAN-2", "csrf_token": csrf_value(staff_client)},
    )
    assert resp.status_code == 200
    assert "keine offenen Reservierungen" in resp.text
    assert "Max Ohne-Reservierung" in resp.text


async def test_scan_unknown_barcode_still_not_found(staff_client):
    resp = await staff_client.post(
        "/scan/lookup",
        data={"barcode": "DOES-NOT-EXIST-ANYWHERE", "csrf_token": csrf_value(staff_client)},
    )
    assert resp.status_code == 200
    assert "Kein Gegenstand oder Material" in resp.text
