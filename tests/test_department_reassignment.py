"""
Regressionstests: Gegenstände/Verbrauchsmaterial ließen sich bisher NUR beim
Anlegen einer Abteilung zuordnen - das Bearbeiten-Formular zeigte das Feld gar
nicht erst an, die Route (update_item/update_consumable) nahm department_id
nicht mal als Parameter entgegen (gemeldeter Bug: "nachträgliches Zuweisen/
Ändern von Abteilungen wird nicht übernommen"). Jetzt nachträglich änderbar,
mit denselben Sicherheitsnetzen wie an vergleichbaren Stellen im Code:
- blockiert bei offener Ausleihe/Reservierung (dieselbe Begründung wie
  purge_item/purge_consumable in app/core/trash.py: Lending/Reservation.
  department_id muss dauerhaft mit item/consumable.department_id
  übereinstimmen, sonst brechen abteilungsgescopte Abfragen anderswo)
- erfordert Mitarbeiter-Rolle in der ZIEL-Abteilung, nicht nur der aktuellen
"""
import pytest_asyncio
from sqlmodel import select

from app.models.common import ItemStatus, UserRole
from app.models.consumable import Consumable
from app.models.consumable_reservation import ConsumableReservation
from app.models.department import Department
from app.models.item import Item
from app.models.lending import Lending
from app.models.reservation import Reservation
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole
from tests.conftest import csrf_value, login


@pytest_asyncio.fixture
async def two_dept_staff_client(client, session_maker, seed_data):
    """Der seed_data-Mitarbeiter bekommt zusätzlich Mitarbeiter-Rolle in einer
    ZWEITEN Abteilung - für Tests, die einen Gegenstand dorthin verschieben."""
    async with session_maker() as session:
        other = Department(code="other-dept", name="Andere Abteilung")
        session.add(other)
        await session.commit()
        await session.refresh(other)

        staff = (await session.exec(select(User).where(User.username == seed_data["staff_username"]))).first()
        session.add(UserDepartmentRole(user_id=staff.id, department_id=other.id, role=UserRole.MITARBEITER))
        await session.commit()
        other_id = other.id

    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    return client, other_id


async def test_update_item_can_change_department(two_dept_staff_client, session_maker, seed_data):
    client, other_department_id = two_dept_staff_client
    async with session_maker() as session:
        item = Item(barcode="MOVE-ITEM-1", name="Akkuschrauber", department_id=seed_data["department_id"])
        session.add(item)
        await session.commit()
        await session.refresh(item)
        item_id = item.id

    resp = await client.post(
        f"/items/{item_id}/edit",
        data={
            "barcode": "MOVE-ITEM-1", "name": "Akkuschrauber",
            "department_id": str(other_department_id),
            "category": "", "location": "", "notes": "", "status": "verfuegbar",
            "csrf_token": csrf_value(client),
        },
    )
    assert resp.status_code == 303, resp.text

    async with session_maker() as session:
        moved = await session.get(Item, item_id)
        assert moved.department_id == other_department_id


async def test_update_item_blocks_department_change_with_open_lending(two_dept_staff_client, session_maker, seed_data):
    client, other_department_id = two_dept_staff_client
    async with session_maker() as session:
        item = Item(barcode="MOVE-ITEM-2", name="Bohrmaschine", department_id=seed_data["department_id"], status=ItemStatus.AUSGELIEHEN)
        worker = User(username="move-worker-1", barcode="MOVE-W1", first_name="Max", last_name="Muster", department_id=seed_data["department_id"])
        session.add(item)
        session.add(worker)
        await session.commit()
        await session.refresh(item)
        await session.refresh(worker)

        session.add(Lending(item_id=item.id, worker_id=worker.id, department_id=seed_data["department_id"]))
        await session.commit()
        item_id = item.id

    resp = await client.post(
        f"/items/{item_id}/edit",
        data={
            "barcode": "MOVE-ITEM-2", "name": "Bohrmaschine",
            "department_id": str(other_department_id),
            "category": "", "location": "", "notes": "", "status": "ausgeliehen",
            "csrf_token": csrf_value(client),
        },
    )
    assert resp.status_code == 409
    assert "offene Ausleihe" in resp.text

    async with session_maker() as session:
        unchanged = await session.get(Item, item_id)
        assert unchanged.department_id == seed_data["department_id"]


async def test_update_item_blocks_department_change_with_open_reservation(two_dept_staff_client, session_maker, seed_data):
    client, other_department_id = two_dept_staff_client
    async with session_maker() as session:
        item = Item(barcode="MOVE-ITEM-3", name="Laser-Entfernungsmesser", department_id=seed_data["department_id"])
        worker = User(username="move-worker-2", barcode="MOVE-W2", first_name="Erika", last_name="Muster", department_id=seed_data["department_id"])
        session.add(item)
        session.add(worker)
        await session.commit()
        await session.refresh(item)
        await session.refresh(worker)

        session.add(Reservation(item_id=item.id, worker_id=worker.id, department_id=seed_data["department_id"]))
        await session.commit()
        item_id = item.id

    resp = await client.post(
        f"/items/{item_id}/edit",
        data={
            "barcode": "MOVE-ITEM-3", "name": "Laser-Entfernungsmesser",
            "department_id": str(other_department_id),
            "category": "", "location": "", "notes": "", "status": "verfuegbar",
            "csrf_token": csrf_value(client),
        },
    )
    assert resp.status_code == 409
    assert "reserviert" in resp.text

    async with session_maker() as session:
        unchanged = await session.get(Item, item_id)
        assert unchanged.department_id == seed_data["department_id"]


async def test_update_item_department_change_requires_staff_role_in_target(session_maker, seed_data, client):
    """Ein Mitarbeiter OHNE Rolle in der Ziel-Abteilung darf einen Gegenstand
    nicht per manipuliertem Formular dorthin verschieben."""
    async with session_maker() as session:
        other = Department(code="locked-dept", name="Gesperrte Abteilung")
        session.add(other)
        await session.commit()
        await session.refresh(other)
        other_id = other.id

        item = Item(barcode="MOVE-ITEM-4", name="Werkzeugkoffer", department_id=seed_data["department_id"])
        session.add(item)
        await session.commit()
        await session.refresh(item)
        item_id = item.id

    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    resp = await client.post(
        f"/items/{item_id}/edit",
        data={
            "barcode": "MOVE-ITEM-4", "name": "Werkzeugkoffer",
            "department_id": str(other_id),
            "category": "", "location": "", "notes": "", "status": "verfuegbar",
            "csrf_token": csrf_value(client),
        },
    )
    assert resp.status_code == 403

    async with session_maker() as session:
        unchanged = await session.get(Item, item_id)
        assert unchanged.department_id == seed_data["department_id"]


async def test_update_consumable_can_change_department(two_dept_staff_client, session_maker, seed_data):
    client, other_department_id = two_dept_staff_client
    async with session_maker() as session:
        consumable = Consumable(barcode="MOVE-CONS-1", name="Schrauben", department_id=seed_data["department_id"])
        session.add(consumable)
        await session.commit()
        await session.refresh(consumable)
        consumable_id = consumable.id

    resp = await client.post(
        f"/consumables/{consumable_id}/edit",
        data={
            "barcode": "MOVE-CONS-1", "name": "Schrauben",
            "department_id": str(other_department_id),
            "category": "", "location": "", "unit": "Stück", "min_quantity": "0",
            "csrf_token": csrf_value(client),
        },
    )
    assert resp.status_code == 303, resp.text

    async with session_maker() as session:
        moved = await session.get(Consumable, consumable_id)
        assert moved.department_id == other_department_id


async def test_update_consumable_blocks_department_change_with_open_reservation(two_dept_staff_client, session_maker, seed_data):
    client, other_department_id = two_dept_staff_client
    async with session_maker() as session:
        consumable = Consumable(barcode="MOVE-CONS-2", name="Kabelbinder", quantity=100, department_id=seed_data["department_id"])
        worker = User(username="move-worker-3", barcode="MOVE-W3", first_name="Erika", last_name="Beispiel", department_id=seed_data["department_id"])
        session.add(consumable)
        session.add(worker)
        await session.commit()
        await session.refresh(consumable)
        await session.refresh(worker)

        session.add(ConsumableReservation(consumable_id=consumable.id, worker_id=worker.id, department_id=seed_data["department_id"], quantity=5))
        await session.commit()
        consumable_id = consumable.id

    resp = await client.post(
        f"/consumables/{consumable_id}/edit",
        data={
            "barcode": "MOVE-CONS-2", "name": "Kabelbinder",
            "department_id": str(other_department_id),
            "category": "", "location": "", "unit": "Stück", "min_quantity": "0",
            "csrf_token": csrf_value(client),
        },
    )
    assert resp.status_code == 409
    assert "vorgemerkt" in resp.text

    async with session_maker() as session:
        unchanged = await session.get(Consumable, consumable_id)
        assert unchanged.department_id == seed_data["department_id"]
