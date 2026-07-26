"""
In-App-Update-Mechanismus (app/core/self_update.py, app/routers/admin_update.py) -
nur für die native Proxmox-LXC-Installation (settings.NATIVE_LXC_DEPLOYMENT).
Echte git/pip/alembic/systemctl-Aufrufe werden hier NIE ausgeführt (würden im
Testlauf weder existieren noch sollen sie den echten Checkout verändern) -
check_for_update/run_update werden per monkeypatch durch Fakes ersetzt, die
Routen selbst (Admin-Gate, NATIVE_LXC_DEPLOYMENT-Gate, CSRF) werden getestet.
"""
import pytest_asyncio

import app.routers.admin_settings as admin_settings_module
import app.routers.admin_update as admin_update_module
from app.core.config import get_settings
from app.core.security import hash_password
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


async def test_settings_page_renders_with_native_lxc_off(admin_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", False)
    resp = await admin_client.get("/admin/settings")
    assert resp.status_code == 200, resp.text
    assert "Portainer" in resp.text


async def test_settings_page_renders_with_native_lxc_on_no_check_yet(admin_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", True)
    resp = await admin_client.get("/admin/settings")
    assert resp.status_code == 200, resp.text
    assert "Noch nicht geprüft" in resp.text


async def test_settings_page_renders_with_cached_update_available(admin_client, monkeypatch):
    from datetime import datetime

    from app.core.self_update import CheckResult

    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", True)
    monkeypatch.setattr(
        admin_settings_module, "get_cached_check",
        lambda: CheckResult(checked_at=datetime(2026, 1, 1, 12, 0), local_commit="a" * 40, remote_commit="b" * 40, update_available=True, error=None),
    )
    resp = await admin_client.get("/admin/settings")
    assert resp.status_code == 200, resp.text
    assert "Update verfügbar" in resp.text
    assert "Jetzt aktualisieren" in resp.text


async def test_settings_page_renders_with_cached_already_up_to_date(admin_client, monkeypatch):
    from datetime import datetime

    from app.core.self_update import CheckResult

    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", True)
    monkeypatch.setattr(
        admin_settings_module, "get_cached_check",
        lambda: CheckResult(checked_at=datetime(2026, 1, 1, 12, 0), local_commit="a" * 40, remote_commit="a" * 40, update_available=False, error=None),
    )
    resp = await admin_client.get("/admin/settings")
    assert resp.status_code == 200, resp.text
    assert "Bereits aktuell" in resp.text
    assert 'action="/admin/update/run"' not in resp.text


async def test_settings_page_renders_with_cached_check_error(admin_client, monkeypatch):
    from datetime import datetime

    from app.core.self_update import CheckResult

    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", True)
    monkeypatch.setattr(
        admin_settings_module, "get_cached_check",
        lambda: CheckResult(checked_at=datetime(2026, 1, 1, 12, 0), local_commit=None, remote_commit=None, update_available=False, error="kein Netzwerk"),
    )
    resp = await admin_client.get("/admin/settings")
    assert resp.status_code == 200, resp.text
    assert "Prüfung fehlgeschlagen" in resp.text


async def test_check_requires_admin(client, seed_data):
    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    resp = await client.post("/admin/update/check", data={"csrf_token": csrf_value(client)})
    assert resp.status_code == 403, resp.text


async def test_check_blocked_without_native_lxc_flag(admin_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", False)
    resp = await admin_client.post("/admin/update/check", data={"csrf_token": csrf_value(admin_client)})
    assert resp.status_code == 403, resp.text


async def test_check_triggers_forced_check_when_enabled(admin_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", True)
    calls = []

    async def _fake_check(force=False):
        calls.append(force)

    monkeypatch.setattr(admin_update_module, "check_for_update", _fake_check)

    resp = await admin_client.post(
        "/admin/update/check", data={"csrf_token": csrf_value(admin_client)}, follow_redirects=False,
    )
    assert resp.status_code == 303, resp.text
    assert calls == [True]


async def test_run_blocked_without_native_lxc_flag(admin_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", False)
    resp = await admin_client.post("/admin/update/run", data={"csrf_token": csrf_value(admin_client)})
    assert resp.status_code == 403, resp.text


async def test_run_requires_admin(client, seed_data):
    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    resp = await client.post("/admin/update/run", data={"csrf_token": csrf_value(client)})
    assert resp.status_code == 403, resp.text


async def test_run_reports_success_from_fake_update(admin_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", True)

    class _FakeResult:
        success = True
        log = "git fetch...\npip install...\nalembic upgrade..."
        error = None

    async def _fake_run():
        return _FakeResult()

    monkeypatch.setattr(admin_update_module, "run_update", _fake_run)

    resp = await admin_client.post("/admin/update/run", data={"csrf_token": csrf_value(admin_client)})
    assert resp.status_code == 200, resp.text
    assert "Update erfolgreich" in resp.text


async def test_run_reports_failure_from_fake_update(admin_client, monkeypatch):
    monkeypatch.setattr(get_settings(), "NATIVE_LXC_DEPLOYMENT", True)

    class _FakeResult:
        success = False
        log = "git fetch...\n"
        error = "pip install fehlgeschlagen (Exit 1)"

    async def _fake_run():
        return _FakeResult()

    monkeypatch.setattr(admin_update_module, "run_update", _fake_run)

    resp = await admin_client.post("/admin/update/run", data={"csrf_token": csrf_value(admin_client)})
    assert resp.status_code == 200, resp.text
    assert "Update fehlgeschlagen" in resp.text
    assert "pip install fehlgeschlagen" in resp.text
