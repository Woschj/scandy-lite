"""
Regressionstests für die Bugfix-Runde nach dem breiten Code-Review (Papierkorb-
Nachfolge): ConsumableReservation-Auto-Erfüllung, Status-Schutz bei offener
Lending, Sammel-Abholung mit IntegrityError-Behandlung, history.py-
Seitenparameter, Barcode-Kollision zwischen Gegenständen und Verbrauchsmaterial.
"""
import pytest_asyncio
from sqlmodel import select

from app.models.common import ItemStatus
from app.models.consumable import Consumable
from app.models.consumable_reservation import ConsumableReservation
from app.models.item import Item
from app.models.lending import Lending
from app.models.reservation import Reservation
from app.models.user import User
from tests.conftest import csrf_value, login


@pytest_asyncio.fixture
async def staff_client(client, seed_data):
    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    return client


async def _get_staff_user(session_maker):
    async with session_maker() as session:
        result = await session.exec(select(User).where(User.barcode == "W-STAFF"))
        return result.first()


async def test_scan_consume_fulfills_own_open_consumable_reservation(staff_client, session_maker, seed_data):
    async with session_maker() as session:
        consumable = Consumable(barcode="CONS-BUGFIX-1", name="Schrauben", quantity=100, department_id=seed_data["department_id"])
        picker = User(
            username="picker-bugfix-1", barcode="W-PICKER-1", first_name="Erika", last_name="Muster",
            department_id=seed_data["department_id"],
        )
        session.add(consumable)
        session.add(picker)
        await session.commit()
        await session.refresh(consumable)
        await session.refresh(picker)

        reservation = ConsumableReservation(
            consumable_id=consumable.id, worker_id=picker.id, department_id=seed_data["department_id"], quantity=5
        )
        session.add(reservation)
        await session.commit()
        await session.refresh(reservation)
        consumable_id, reservation_id = consumable.id, reservation.id

    resp = await staff_client.post(
        "/scan/consume",
        data={
            "consumable_id": str(consumable_id),
            "quantity": "5",
            "worker_barcode": "W-PICKER-1",
            "csrf_token": csrf_value(staff_client),
        },
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        updated = await session.get(ConsumableReservation, reservation_id)
        assert updated.fulfilled_at is not None


async def test_update_item_blocks_status_change_with_open_lending(staff_client, session_maker, seed_data):
    staff_worker = await _get_staff_user(session_maker)
    async with session_maker() as session:
        item = Item(barcode="ITEM-LEND-BUGFIX-1", name="Bohrer", department_id=seed_data["department_id"], status=ItemStatus.AUSGELIEHEN)
        session.add(item)
        await session.commit()
        await session.refresh(item)

        lending = Lending(item_id=item.id, worker_id=staff_worker.id, department_id=seed_data["department_id"])
        session.add(lending)
        await session.commit()
        item_id = item.id

    resp = await staff_client.post(
        f"/items/{item_id}/edit",
        data={
            "barcode": "ITEM-LEND-BUGFIX-1",
            "name": "Bohrer",
            "department_id": str(seed_data["department_id"]),
            "category": "",
            "location": "",
            "notes": "",
            "status": "defekt",
            "csrf_token": csrf_value(staff_client),
        },
    )
    assert resp.status_code == 409
    assert "offene Ausleihe" in resp.text

    async with session_maker() as session:
        unchanged = await session.get(Item, item_id)
        assert unchanged.status == ItemStatus.AUSGELIEHEN


async def test_pickup_confirm_handles_integrity_error_gracefully(staff_client, session_maker, seed_data):
    staff_worker = await _get_staff_user(session_maker)
    async with session_maker() as session:
        picker = User(username="picker-bugfix-2", barcode="W-PICKER-2", first_name="Pick", last_name="Up", department_id=seed_data["department_id"])
        item = Item(barcode="ITEM-PICKUP-BUGFIX-1", name="Akkuschrauber", department_id=seed_data["department_id"])
        session.add(picker)
        session.add(item)
        await session.commit()
        await session.refresh(picker)
        await session.refresh(item)

        reservation = Reservation(item_id=item.id, worker_id=picker.id, department_id=seed_data["department_id"])
        session.add(reservation)

        # Fabrizierter Konflikt: Gegenstand zeigt (noch) "verfügbar", hat aber
        # bereits eine offene Lending - simuliert exakt den Zustand, der bei
        # einem echten Race zwischen Vor-Prüfung und Commit entstehen könnte.
        conflicting_lending = Lending(item_id=item.id, worker_id=staff_worker.id, department_id=seed_data["department_id"])
        session.add(conflicting_lending)
        await session.commit()
        await session.refresh(reservation)

        picker_id, reservation_id = picker.id, reservation.id

    signature = "data:image/png;base64," + ("A" * 20)
    resp = await staff_client.post(
        f"/scan/pickup/{picker_id}/confirm",
        data={"checked": str(reservation_id), "signature": signature, "csrf_token": csrf_value(staff_client)},
    )
    assert resp.status_code == 303
    assert "error=" in resp.headers["location"]


async def test_history_page_zero_does_not_break(staff_client):
    resp = await staff_client.get("/history?page=0")
    assert resp.status_code == 200


async def test_history_negative_page_does_not_break(staff_client):
    resp = await staff_client.get("/history?page=-5")
    assert resp.status_code == 200


async def test_history_search_finds_entry_by_item_barcode(staff_client, session_maker, seed_data):
    """Regressionstest: die Detailseiten verlinken 'Vollständige Historie
    ansehen' mit dem Barcode als Suchbegriff (siehe items/detail.html,
    consumables/detail.html) - die Freitextsuche muss Barcodes deshalb
    tatsächlich durchsuchen, nicht nur Namen (vorher landete man bei diesem
    Link auf einer leeren Ergebnisliste)."""
    async with session_maker() as session:
        staff_worker = (await session.exec(select(User).where(User.barcode == "W-STAFF"))).first()
        item = Item(barcode="HIST-SEARCH-1", name="Suchbarer Akkuschrauber", department_id=seed_data["department_id"])
        session.add(item)
        await session.commit()
        await session.refresh(item)

        lending = Lending(
            item_id=item.id, worker_id=staff_worker.id, department_id=seed_data["department_id"],
        )
        session.add(lending)
        await session.commit()

    resp = await staff_client.get("/history?q=HIST-SEARCH-1")
    assert resp.status_code == 200
    assert "Suchbarer Akkuschrauber" in resp.text


async def test_create_item_blocked_by_existing_consumable_barcode(staff_client, session_maker, seed_data):
    async with session_maker() as session:
        session.add(Consumable(barcode="SHARED-BUGFIX-1", name="Material", department_id=seed_data["department_id"]))
        await session.commit()

    resp = await staff_client.post(
        "/items/new",
        data={
            "department_id": str(seed_data["department_id"]),
            "barcode": "SHARED-BUGFIX-1",
            "name": "Gegenstand",
            "category": "", "location": "", "notes": "",
            "csrf_token": csrf_value(staff_client),
        },
    )
    assert resp.status_code == 409
    assert "bereits vergeben" in resp.text


async def test_create_consumable_blocked_by_existing_item_barcode(staff_client, session_maker, seed_data):
    async with session_maker() as session:
        session.add(Item(barcode="SHARED-BUGFIX-2", name="Gegenstand", department_id=seed_data["department_id"]))
        await session.commit()

    resp = await staff_client.post(
        "/consumables/new",
        data={
            "department_id": str(seed_data["department_id"]),
            "barcode": "SHARED-BUGFIX-2",
            "name": "Material",
            "category": "", "location": "", "unit": "Stück", "quantity": "0", "min_quantity": "0",
            "csrf_token": csrf_value(staff_client),
        },
    )
    assert resp.status_code == 409
    assert "bereits vergeben" in resp.text
