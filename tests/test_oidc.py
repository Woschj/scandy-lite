"""
SSO/OIDC (app.core.oidc, app.routers.oidc, app.routers.admin_settings
pending-accounts): der volle Redirect-Handshake gegen einen echten Identity-
Provider lässt sich hier nicht durchspielen, daher testgetrennt:
- unique_username_from_claims als reine Funktion (Kollisions-Vermeidung),
- Freischalten/Ablehnen/Auflisten als normale, direkt aufrufbare Admin-Routen
  (JIT-Konto wird wie beim echten Callback manuell mit approved_at=None
  angelegt statt den Callback selbst zu simulieren),
- /auth/oidc/* antwortet mit 403, solange OIDC_ISSUER/CLIENT_ID/SECRET nicht
  gesetzt sind (Standard in Tests) - das Feature ist per Default aus.
"""
import uuid

import pytest_asyncio
from sqlmodel import select

from app.core.oidc import unique_username_from_claims
from app.core.security import hash_password
from app.models.common import AuthSource, UserRole, utcnow
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole
from tests.conftest import csrf_value, login


@pytest_asyncio.fixture
async def admin_client(client, session_maker):
    async with session_maker() as session:
        admin = User(username="admin", is_admin=True, hashed_password=hash_password("adminpass123"), approved_at=utcnow())
        session.add(admin)
        await session.commit()
    await login(client, "admin", "adminpass123")
    return client


async def _create_pending_user(session_maker, *, username: str, sub: str) -> uuid.UUID:
    async with session_maker() as session:
        user = User(
            username=username, email=f"{username}@example.com",
            first_name="SSO", last_name=username,
            auth_source=AuthSource.SSO, external_id=sub,
            is_active=False, approved_at=None,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user.id


# --- unique_username_from_claims -----------------------------------------

async def test_unique_username_prefers_preferred_username(session_maker):
    async with session_maker() as session:
        name = await unique_username_from_claims(session, {"preferred_username": "MMuster"}, "sub-1")
    assert name == "mmuster"


async def test_unique_username_appends_suffix_on_preferred_username_collision(session_maker):
    """Kollision wird zuerst durch Zahlen-Suffixe am BEVORZUGTEN Namen
    aufgelöst (mmuster -> mmuster1), nicht durch sofortigen Wechsel auf die
    E-Mail - der Name bleibt so erkennbar "mmuster-artig" statt unvermittelt
    einer anderen Quelle zu entstammen."""
    async with session_maker() as session:
        session.add(User(username="mmuster"))
        await session.commit()

        name = await unique_username_from_claims(
            session, {"preferred_username": "mmuster", "email": "erika@example.com"}, "sub-2"
        )
    assert name == "mmuster1"


async def test_unique_username_uses_email_when_no_preferred_username(session_maker):
    async with session_maker() as session:
        name = await unique_username_from_claims(session, {"email": "erika@example.com"}, "sub-2b")
    assert name == "erika"


async def test_unique_username_appends_suffix_when_all_taken(session_maker):
    async with session_maker() as session:
        session.add(User(username="mmuster"))
        session.add(User(username="mmuster1"))
        await session.commit()

        name = await unique_username_from_claims(session, {"preferred_username": "mmuster"}, "sub-3")
    assert name == "mmuster2"


async def test_unique_username_falls_back_to_sub_without_any_claims(session_maker):
    async with session_maker() as session:
        name = await unique_username_from_claims(session, {}, "abcdefgh12345678")
    assert name == "sso-abcdefgh"


# --- /auth/oidc/* Feature-Gate (SSO standardmässig aus) -------------------

async def test_oidc_login_disabled_by_default(client):
    resp = await client.get("/auth/oidc/login", follow_redirects=False)
    assert resp.status_code == 403


async def test_oidc_callback_disabled_by_default(client):
    resp = await client.get("/auth/oidc/callback", follow_redirects=False)
    assert resp.status_code == 403


# --- Ausstehende Konten: Liste/Freischalten/Ablehnen -----------------------

async def test_pending_accounts_lists_only_unapproved(admin_client, session_maker, seed_data):
    pending_id = await _create_pending_user(session_maker, username="pending-1", sub="sub-p1")

    resp = await admin_client.get("/admin/pending-accounts")
    assert resp.status_code == 200
    assert str(pending_id) in resp.text
    # seed_data legt einen bereits freigeschalteten Mitarbeiter an (siehe
    # tests/conftest.py) - der darf hier nicht als "ausstehend" auftauchen.
    assert seed_data["staff_username"] not in resp.text


async def test_non_admin_cannot_see_pending_accounts(client, seed_data):
    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    resp = await client.get("/admin/pending-accounts", follow_redirects=False)
    assert resp.status_code == 403


async def test_approve_pending_account_sets_department_and_role(admin_client, session_maker, seed_data):
    pending_id = await _create_pending_user(session_maker, username="pending-2", sub="sub-p2")

    resp = await admin_client.post(
        f"/admin/pending-accounts/{pending_id}/approve",
        data={
            "department_id": str(seed_data["department_id"]),
            "initial_role": "mitarbeiter",
            "csrf_token": csrf_value(admin_client),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        approved = await session.get(User, pending_id)
        assert approved.approved_at is not None
        assert approved.is_active is True
        assert approved.department_id == seed_data["department_id"]

        role_result = await session.exec(
            select(UserDepartmentRole).where(
                UserDepartmentRole.user_id == pending_id, UserDepartmentRole.department_id == seed_data["department_id"]
            )
        )
        role = role_result.first()
        assert role is not None
        assert role.role == UserRole.MITARBEITER


async def test_approve_pending_account_without_role_creates_no_role(admin_client, session_maker, seed_data):
    pending_id = await _create_pending_user(session_maker, username="pending-3", sub="sub-p3")

    resp = await admin_client.post(
        f"/admin/pending-accounts/{pending_id}/approve",
        data={
            "department_id": str(seed_data["department_id"]),
            "initial_role": "",
            "csrf_token": csrf_value(admin_client),
        },
        follow_redirects=False,
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        approved = await session.get(User, pending_id)
        assert approved.approved_at is not None

        role_result = await session.exec(select(UserDepartmentRole).where(UserDepartmentRole.user_id == pending_id))
        assert role_result.first() is None


async def test_reject_pending_account_deletes_it(admin_client, session_maker, seed_data):
    pending_id = await _create_pending_user(session_maker, username="pending-4", sub="sub-p4")

    resp = await admin_client.post(
        f"/admin/pending-accounts/{pending_id}/reject",
        data={"csrf_token": csrf_value(admin_client)},
        follow_redirects=False,
    )
    assert resp.status_code == 303

    async with session_maker() as session:
        assert await session.get(User, pending_id) is None


# --- Dashboard-Hinweis -----------------------------------------------------

async def test_dashboard_shows_pending_banner_for_admin(admin_client, session_maker, seed_data):
    await _create_pending_user(session_maker, username="pending-5", sub="sub-p5")

    resp = await admin_client.get("/")
    assert resp.status_code == 200
    assert "Aktion nötig" in resp.text


async def test_dashboard_hides_pending_banner_without_pending_accounts(admin_client):
    resp = await admin_client.get("/")
    assert resp.status_code == 200
    assert "Aktion nötig" not in resp.text


async def test_dashboard_hides_pending_banner_for_non_admin(client, session_maker, seed_data):
    await _create_pending_user(session_maker, username="pending-6", sub="sub-p6")
    await login(client, seed_data["staff_username"], seed_data["staff_password"])

    resp = await client.get("/")
    assert resp.status_code == 200
    assert "Aktion nötig" not in resp.text
