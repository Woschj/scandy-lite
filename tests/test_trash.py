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
from app.core.trash import purge_item, purge_user, restore_item, restore_user
from app.models.common import utcnow
from app.models.department import Department
from app.models.item import Item
from app.models.lending import Lending
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


async def test_department_deletable_after_purging_last_blocking_item(admin_client, session_maker):
    async with session_maker() as session:
        department = Department(code="trashdept", name="TrashDept")
        session.add(department)
        await session.commit()
        await session.refresh(department)
        department_id = department.id

        item = Item(barcode="TRASH-3", name="Letzter Rest", department_id=department_id, deleted_at=utcnow())
        session.add(item)
        await session.commit()
        await session.refresh(item)
        item_id = item.id

    blocked_resp = await admin_client.post(
        f"/admin/departments/{department_id}/delete", data={"csrf_token": csrf_value(admin_client)}
    )
    assert blocked_resp.status_code == 303
    assert "error=" in blocked_resp.headers["location"]

    purge_resp = await admin_client.post(
        f"/admin/trash/items/{item_id}/purge", data={"csrf_token": csrf_value(admin_client)}
    )
    assert purge_resp.status_code == 303
    assert "error=" not in purge_resp.headers["location"]

    delete_resp = await admin_client.post(
        f"/admin/departments/{department_id}/delete", data={"csrf_token": csrf_value(admin_client)}
    )
    assert delete_resp.status_code == 303
    assert "error=" not in delete_resp.headers["location"]

    async with session_maker() as session:
        assert await session.get(Department, department_id) is None


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
