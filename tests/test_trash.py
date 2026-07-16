"""
Regressionstests für den Papierkorb (app.core.trash): endgültiges Löschen
("purge") snapshottet Name/Barcode in abgeschlossene Ausleih-Historie statt
sie zu zerreißen, blockiert aber bei noch OFFENEN Ausleihen/Reservierungen.
Deckt außerdem den ursprünglichen Auslöser ab: eine Abteilung mit nur noch
gepurgten Einträgen muss danach löschbar sein.
"""
from datetime import timedelta

import pytest_asyncio

from app.core.security import hash_password
from app.core.trash import purge_department, purge_item, purge_user, restore_item, restore_user
from app.models.common import utcnow
from app.models.consumable import Consumable, ConsumableUsage
from app.models.department import Department
from app.models.item import Item
from app.models.lending import Lending
from app.models.preset import Category, Location
from app.models.user import User
from tests.conftest import csrf_value, login


@pytest_asyncio.fixture
async def admin_client(client, session_maker):
    async with session_maker() as session:
        admin = User(username="admin", is_admin=True, hashed_password=hash_password("adminpass123"))
        session.add(admin)
        await session.commit()
    await login(client, "admin", "adminpass123")
    return client


async def test_purge_item_snapshots_closed_lending_and_deletes_item(session_maker, seed_data):
    async with session_maker() as session:
        item = Item(barcode="TRASH-1", name="Alter Bohrer", department_id=seed_data["department_id"], deleted_at=utcnow())
        worker = User(username="trash-w1", barcode="TRASH-W1", first_name="Max", last_name="Muster", department_id=seed_data["department_id"])
        session.add(item)
        session.add(worker)
        await session.commit()
        await session.refresh(item)
        await session.refresh(worker)

        lending = Lending(
            item_id=item.id, worker_id=worker.id, department_id=seed_data["department_id"],
            lent_at=utcnow() - timedelta(days=2), returned_at=utcnow() - timedelta(days=1),
        )
        session.add(lending)
        await session.commit()
        await session.refresh(lending)
        item_id, lending_id = item.id, lending.id

    async with session_maker() as session:
        item = await session.get(Item, item_id)
        error = await purge_item(session, item)
        assert error is None
        await session.commit()

    async with session_maker() as session:
        assert await session.get(Item, item_id) is None
        updated_lending = await session.get(Lending, lending_id)
        assert updated_lending.item_id is None
        assert updated_lending.item_name_snapshot == "Alter Bohrer"
        assert updated_lending.item_barcode_snapshot == "TRASH-1"


async def test_purge_item_blocked_by_open_lending(session_maker, seed_data):
    async with session_maker() as session:
        item = Item(barcode="TRASH-2", name="Aktiver Akkuschrauber", department_id=seed_data["department_id"], deleted_at=utcnow())
        worker = User(username="trash-w2", barcode="TRASH-W2", first_name="Erika", last_name="Muster", department_id=seed_data["department_id"])
        session.add(item)
        session.add(worker)
        await session.commit()
        await session.refresh(item)
        await session.refresh(worker)

        open_lending = Lending(item_id=item.id, worker_id=worker.id, department_id=seed_data["department_id"])
        session.add(open_lending)
        await session.commit()
        item_id = item.id

    async with session_maker() as session:
        item = await session.get(Item, item_id)
        error = await purge_item(session, item)
        assert error is not None
        assert "offene Ausleihe" in error

    async with session_maker() as session:
        assert await session.get(Item, item_id) is not None


async def test_restore_item_blocked_by_barcode_taken_by_active_item(session_maker, seed_data):
    async with session_maker() as session:
        old_item = Item(barcode="DUP-1", name="Alt", department_id=seed_data["department_id"], deleted_at=utcnow())
        new_item = Item(barcode="DUP-1", name="Neu angelegt", department_id=seed_data["department_id"])
        session.add(old_item)
        session.add(new_item)
        await session.commit()
        await session.refresh(old_item)
        old_item_id = old_item.id

    async with session_maker() as session:
        item = await session.get(Item, old_item_id)
        error = await restore_item(session, item)
        assert error is not None
        assert "neu vergeben" in error

    async with session_maker() as session:
        still_deleted = await session.get(Item, old_item_id)
        assert still_deleted.deleted_at is not None


async def test_department_delete_cascades_and_preserves_closed_history(admin_client, session_maker):
    """Löschen einer Abteilung darf nicht mehr bei jeder noch referenzierenden
    Zeile blockieren (siehe app.core.trash.purge_department) - Gegenstände/
    Verbrauchsmaterial/Kategorien/Standorte werden mitgelöscht, ABGESCHLOSSENE
    Historie bleibt aber als Text-Schnappschuss erhalten statt zu verschwinden."""
    async with session_maker() as session:
        department = Department(code="trashdept", name="TrashDept")
        session.add(department)
        await session.commit()
        await session.refresh(department)
        department_id = department.id

        item = Item(barcode="TRASH-3", name="Letzter Rest", department_id=department_id)
        worker = User(username="trashdept-worker", barcode="TRASH-3-W", first_name="Rest", last_name="Arbeiter", department_id=department_id)
        category = Category(name="Restkategorie", department_id=department_id)
        location = Location(name="Restregal", department_id=department_id)
        session.add(item)
        session.add(worker)
        session.add(category)
        session.add(location)
        await session.commit()
        await session.refresh(item)
        await session.refresh(worker)

        # Abgeschlossene (nicht offene) Ausleihe - darf NICHT blockieren, muss
        # aber als Text-Schnappschuss erhalten bleiben.
        lending = Lending(
            item_id=item.id, worker_id=worker.id, department_id=department_id,
            lent_at=utcnow() - timedelta(days=2), returned_at=utcnow() - timedelta(days=1),
        )
        session.add(lending)
        await session.commit()
        await session.refresh(lending)
        item_id, worker_id, category_id, location_id, lending_id = item.id, worker.id, category.id, location.id, lending.id

    delete_resp = await admin_client.post(
        f"/admin/departments/{department_id}/delete", data={"csrf_token": csrf_value(admin_client)}
    )
    assert delete_resp.status_code == 303
    assert "error=" not in delete_resp.headers["location"], delete_resp.headers["location"]

    async with session_maker() as session:
        assert await session.get(Department, department_id) is None
        assert await session.get(Item, item_id) is None
        assert await session.get(User, worker_id) is None
        assert await session.get(Category, category_id) is None
        assert await session.get(Location, location_id) is None

        preserved_lending = await session.get(Lending, lending_id)
        assert preserved_lending is not None
        assert preserved_lending.department_id is None
        assert preserved_lending.department_name_snapshot == "TrashDept"
        assert preserved_lending.item_name_snapshot == "Letzter Rest"
        assert preserved_lending.worker_name_snapshot == "Rest Arbeiter"


async def test_department_delete_blocked_by_open_lending(admin_client, session_maker):
    async with session_maker() as session:
        department = Department(code="opendept", name="OpenDept")
        session.add(department)
        await session.commit()
        await session.refresh(department)
        department_id = department.id

        item = Item(barcode="OPEN-DEPT-ITEM", name="Noch ausgeliehen", department_id=department_id)
        worker = User(username="opendept-worker", barcode="OPEN-DEPT-W", first_name="Noch", last_name="Aktiv", department_id=department_id)
        session.add(item)
        session.add(worker)
        await session.commit()
        await session.refresh(item)
        await session.refresh(worker)

        open_lending = Lending(item_id=item.id, worker_id=worker.id, department_id=department_id)
        session.add(open_lending)
        await session.commit()

    resp = await admin_client.post(
        f"/admin/departments/{department_id}/delete", data={"csrf_token": csrf_value(admin_client)}
    )
    assert resp.status_code == 303
    assert "error=" in resp.headers["location"]

    async with session_maker() as session:
        assert await session.get(Department, department_id) is not None


async def test_purge_department_snapshots_closed_consumable_usage(session_maker):
    async with session_maker() as session:
        department = Department(code="consdept", name="ConsDept")
        session.add(department)
        await session.commit()
        await session.refresh(department)

        consumable = Consumable(barcode="CONS-DEPT-1", name="Schrauben", quantity=100, department_id=department.id)
        session.add(consumable)
        await session.commit()
        await session.refresh(consumable)

        usage = ConsumableUsage(consumable_id=consumable.id, department_id=department.id, quantity=5)
        session.add(usage)
        await session.commit()
        await session.refresh(usage)
        department_id, usage_id = department.id, usage.id

    async with session_maker() as session:
        department = await session.get(Department, department_id)
        error = await purge_department(session, department)
        assert error is None
        await session.commit()

    async with session_maker() as session:
        assert await session.get(Department, department_id) is None
        preserved_usage = await session.get(ConsumableUsage, usage_id)
        assert preserved_usage.department_id is None
        assert preserved_usage.department_name_snapshot == "ConsDept"
        assert preserved_usage.consumable_name_snapshot == "Schrauben"


async def test_settings_page_renders_with_trash_entries(admin_client, session_maker, seed_data):
    async with session_maker() as session:
        session.add(Item(barcode="TRASH-4", name="Zu sehen im Papierkorb", department_id=seed_data["department_id"], deleted_at=utcnow()))
        await session.commit()

    resp = await admin_client.get("/admin/settings")
    assert resp.status_code == 200
    assert "Zu sehen im Papierkorb" in resp.text


async def test_purge_user_snapshots_closed_lending_and_deletes_user(session_maker, seed_data):
    async with session_maker() as session:
        worker = User(
            username="trash-w3", barcode="TRASH-W3", first_name="Alt", last_name="Belegschaft",
            department_id=seed_data["department_id"], deleted_at=utcnow(),
        )
        item = Item(barcode="TRASH-ITEM-W3", name="Schrauber", department_id=seed_data["department_id"])
        session.add(worker)
        session.add(item)
        await session.commit()
        await session.refresh(worker)
        await session.refresh(item)

        lending = Lending(
            item_id=item.id, worker_id=worker.id, department_id=seed_data["department_id"],
            lent_at=utcnow() - timedelta(days=2), returned_at=utcnow() - timedelta(days=1),
        )
        session.add(lending)
        await session.commit()
        await session.refresh(lending)
        worker_id, lending_id = worker.id, lending.id

    async with session_maker() as session:
        worker = await session.get(User, worker_id)
        error = await purge_user(session, worker)
        assert error is None
        await session.commit()

    async with session_maker() as session:
        assert await session.get(User, worker_id) is None
        updated_lending = await session.get(Lending, lending_id)
        assert updated_lending.worker_id is None
        assert updated_lending.worker_name_snapshot == "Alt Belegschaft"


async def test_purge_user_blocked_by_open_lending(session_maker, seed_data):
    async with session_maker() as session:
        worker = User(
            username="trash-w4", barcode="TRASH-W4", first_name="Noch", last_name="Aktiv",
            department_id=seed_data["department_id"], deleted_at=utcnow(),
        )
        item = Item(barcode="TRASH-ITEM-W4", name="Bohrer", department_id=seed_data["department_id"])
        session.add(worker)
        session.add(item)
        await session.commit()
        await session.refresh(worker)
        await session.refresh(item)

        open_lending = Lending(item_id=item.id, worker_id=worker.id, department_id=seed_data["department_id"])
        session.add(open_lending)
        await session.commit()
        worker_id = worker.id

    async with session_maker() as session:
        worker = await session.get(User, worker_id)
        error = await purge_user(session, worker)
        assert error is not None
        assert "offene Ausleihe" in error

    async with session_maker() as session:
        assert await session.get(User, worker_id) is not None


async def test_restore_user_blocked_by_barcode_taken_by_active_user(session_maker, seed_data):
    async with session_maker() as session:
        old_user = User(
            username="trash-w5-old", barcode="DUP-W5", first_name="Alt", last_name="Belegschaft",
            department_id=seed_data["department_id"], deleted_at=utcnow(),
        )
        new_user = User(
            username="trash-w5-new", barcode="DUP-W5", first_name="Neu", last_name="Angelegt",
            department_id=seed_data["department_id"],
        )
        session.add(old_user)
        session.add(new_user)
        await session.commit()
        await session.refresh(old_user)
        old_user_id = old_user.id

    async with session_maker() as session:
        worker = await session.get(User, old_user_id)
        error = await restore_user(session, worker)
        assert error is not None
        assert "neu vergeben" in error

    async with session_maker() as session:
        still_deleted = await session.get(User, old_user_id)
        assert still_deleted.deleted_at is not None
