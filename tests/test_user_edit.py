"""
Regressionstest für die vereinheitlichte Benutzer-Bearbeiten-Seite
(app.routers.admin_settings.update_user): Login- (Benutzername/E-Mail/
Passwort/Admin) UND Ausweis-Stammdaten (Vorname/Nachname/Barcode/Abteilung)
sind jetzt Felder DESSELBEN Users (siehe app/models/user.py) und werden in
einem einzigen POST gespeichert. Deckt außerdem ab, dass eine E-Mail-Adresse
nachträglich ergänzt werden kann, auch wenn sie beim Anlegen leer gelassen wurde.
"""
import pytest_asyncio
from sqlmodel import select

from app.core.security import hash_password
from app.models.common import UserRole
from app.models.department import Department
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole
from tests.conftest import csrf_value, login


@pytest_asyncio.fixture
async def admin_logged_in(client, session_maker):
    async with session_maker() as session:
        admin = User(username="admin", is_admin=True, hashed_password=hash_password("adminpass123"))
        session.add(admin)
        await session.commit()
    await login(client, "admin", "adminpass123")
    return client


async def _get_user_id_by_username(session_maker, username: str):
    async with session_maker() as session:
        result = await session.exec(select(User).where(User.username == username))
        return result.first().id


async def test_update_user_saves_login_and_worker_fields_together(admin_logged_in, session_maker, seed_data):
    client = admin_logged_in

    async with session_maker() as session:
        second_department = Department(code="buero", name="Büro")
        session.add(second_department)
        await session.commit()
        await session.refresh(second_department)
        second_department_id = second_department.id

    staff_user_id = await _get_user_id_by_username(session_maker, "staff")

    payload = {
        "username": "staff-renamed",
        "email": "staff@test.local",
        "new_password": "",
        "first_name": "Erika",
        "last_name": "Musterfrau",
        "barcode": "W-STAFF-NEW",
        "department_id": str(second_department_id),
        "csrf_token": csrf_value(client),
    }
    resp = await client.post(f"/admin/users/{staff_user_id}/edit", data=payload)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/admin/settings#users"

    async with session_maker() as session:
        updated_user = await session.get(User, staff_user_id)
        assert updated_user.username == "staff-renamed"
        assert updated_user.email == "staff@test.local"
        assert updated_user.first_name == "Erika"
        assert updated_user.last_name == "Musterfrau"
        assert updated_user.barcode == "W-STAFF-NEW"
        assert updated_user.department_id == second_department_id


async def test_update_user_rejects_barcode_already_used_by_another_user(admin_logged_in, session_maker, seed_data):
    client = admin_logged_in

    async with session_maker() as session:
        other_worker = User(
            username="other-worker", barcode="W-TAKEN", first_name="Other", last_name="Worker",
            department_id=seed_data["department_id"],
        )
        session.add(other_worker)
        await session.commit()

    staff_user_id = await _get_user_id_by_username(session_maker, "staff")

    payload = {
        "username": "staff",
        "email": "",
        "new_password": "",
        "first_name": "Staff",
        "last_name": "Worker",
        "barcode": "W-TAKEN",
        "department_id": str(seed_data["department_id"]),
        "csrf_token": csrf_value(client),
    }
    resp = await client.post(f"/admin/users/{staff_user_id}/edit", data=payload)
    assert resp.status_code == 303
    assert "error=" in resp.headers["location"]

    async with session_maker() as session:
        untouched_user = await session.get(User, staff_user_id)
        assert untouched_user.barcode != "W-TAKEN"


async def test_update_user_moves_access_role_to_new_home_department(admin_logged_in, session_maker, seed_data):
    """Gemeldeter Bug: Heimat-Abteilung (Ausweis) ändern schien zu klappen,
    aber im Zugriff-Tab blieb der Mitarbeiter an der ALTEN Abteilung hängen -
    department_id und UserDepartmentRole sind getrennte Datensätze, die
    Rolle muss beim Wechsel der Heimat-Abteilung mitwandern."""
    client = admin_logged_in

    async with session_maker() as session:
        second_department = Department(code="buero-move", name="Büro Move")
        session.add(second_department)
        await session.commit()
        await session.refresh(second_department)
        second_department_id = second_department.id

    staff_user_id = await _get_user_id_by_username(session_maker, "staff")

    payload = {
        "username": "staff", "email": "", "new_password": "",
        "first_name": "Staff", "last_name": "Worker", "barcode": "W-STAFF",
        "department_id": str(second_department_id),
        "csrf_token": csrf_value(client),
    }
    resp = await client.post(f"/admin/users/{staff_user_id}/edit", data=payload)
    assert resp.status_code == 303

    async with session_maker() as session:
        old_role = await session.get(UserDepartmentRole, (staff_user_id, seed_data["department_id"]))
        assert old_role is None, "Rolle an der alten Abteilung haette entfernt werden muessen"

        new_role = await session.get(UserDepartmentRole, (staff_user_id, second_department_id))
        assert new_role is not None, "Rolle haette zur neuen Heimat-Abteilung mitwandern muessen"
        assert new_role.role == UserRole.MITARBEITER


async def test_update_user_home_department_move_keeps_other_department_roles(admin_logged_in, session_maker, seed_data):
    """Eine ZUSÄTZLICHE Rolle in einer dritten (nicht der Heimat-)Abteilung
    darf beim Wechsel der Heimat-Abteilung nicht angetastet werden."""
    client = admin_logged_in

    async with session_maker() as session:
        third_department = Department(code="dritte-abt", name="Dritte Abteilung")
        new_home = Department(code="neue-heimat", name="Neue Heimat")
        session.add(third_department)
        session.add(new_home)
        await session.commit()
        await session.refresh(third_department)
        await session.refresh(new_home)

        staff_user_id = await _get_user_id_by_username(session_maker, "staff")
        session.add(UserDepartmentRole(user_id=staff_user_id, department_id=third_department.id, role=UserRole.NUTZER))
        await session.commit()
        third_department_id, new_home_id = third_department.id, new_home.id

    payload = {
        "username": "staff", "email": "", "new_password": "",
        "first_name": "Staff", "last_name": "Worker", "barcode": "W-STAFF",
        "department_id": str(new_home_id),
        "csrf_token": csrf_value(client),
    }
    resp = await client.post(f"/admin/users/{staff_user_id}/edit", data=payload)
    assert resp.status_code == 303

    async with session_maker() as session:
        third_role = await session.get(UserDepartmentRole, (staff_user_id, third_department_id))
        assert third_role is not None
        assert third_role.role == UserRole.NUTZER

        new_home_role = await session.get(UserDepartmentRole, (staff_user_id, new_home_id))
        assert new_home_role is not None
        assert new_home_role.role == UserRole.MITARBEITER


async def test_update_user_home_department_move_does_not_overwrite_existing_role_at_target(admin_logged_in, session_maker, seed_data):
    """Existiert an der NEUEN Heimat-Abteilung bereits eine eigene (im
    Zugriff-Tab bewusst gesetzte) Rolle, gewinnt die - die alte Rolle an der
    bisherigen Heimat-Abteilung wird nur aufgeräumt, nicht überschrieben."""
    client = admin_logged_in

    async with session_maker() as session:
        new_home = Department(code="ziel-mit-rolle", name="Ziel mit Rolle")
        session.add(new_home)
        await session.commit()
        await session.refresh(new_home)
        new_home_id = new_home.id

        staff_user_id = await _get_user_id_by_username(session_maker, "staff")
        session.add(UserDepartmentRole(user_id=staff_user_id, department_id=new_home_id, role=UserRole.NUTZER))
        await session.commit()

    payload = {
        "username": "staff", "email": "", "new_password": "",
        "first_name": "Staff", "last_name": "Worker", "barcode": "W-STAFF",
        "department_id": str(new_home_id),
        "csrf_token": csrf_value(client),
    }
    resp = await client.post(f"/admin/users/{staff_user_id}/edit", data=payload)
    assert resp.status_code == 303

    async with session_maker() as session:
        old_role = await session.get(UserDepartmentRole, (staff_user_id, seed_data["department_id"]))
        assert old_role is None

        target_role = await session.get(UserDepartmentRole, (staff_user_id, new_home_id))
        assert target_role is not None
        assert target_role.role == UserRole.NUTZER, "bereits gesetzte Rolle an der Ziel-Abteilung darf nicht ueberschrieben werden"


async def test_update_user_can_add_email_that_was_empty_at_creation(admin_logged_in, session_maker, seed_data):
    async with session_maker() as session:
        plain_user = User(
            username="noemail", is_admin=False, hashed_password=hash_password("somepassword123"),
            barcode="W-NOEMAIL", first_name="Kein", last_name="Mail", department_id=seed_data["department_id"],
        )
        session.add(plain_user)
        await session.commit()
        await session.refresh(plain_user)
        plain_user_id = plain_user.id
        assert plain_user.email is None

    payload = {
        "username": "noemail",
        "email": "added-later@test.local",
        "new_password": "",
        "first_name": "Kein",
        "last_name": "Mail",
        "barcode": "W-NOEMAIL",
        "department_id": str(seed_data["department_id"]),
        "csrf_token": csrf_value(admin_logged_in),
    }
    resp = await admin_logged_in.post(f"/admin/users/{plain_user_id}/edit", data=payload)
    assert resp.status_code == 303

    async with session_maker() as session:
        updated = await session.get(User, plain_user_id)
        assert updated.email == "added-later@test.local"
