"""
Regressionstests für den Passwort-Reset-Flow (app.routers.auth) und die
Willkommens-Mail beim Anlegen eines Benutzers (app.routers.admin_settings).

smtplib wird nie wirklich angesprochen - app.core.email._send_sync wird per
monkeypatch auf ein Fake umgebogen, das die verschickten Mails nur aufzeichnet
(siehe sent_emails-Fixture unten). Das prüft den kompletten Pfad bis kurz vor
den echten Netzwerk-Versand, ohne einen SMTP-Server zu brauchen.
"""
import re
from datetime import timedelta

import pytest
import pytest_asyncio

from app.core import email as email_module
from app.core.crypto import hash_token
from app.core.security import hash_password
from app.models.common import utcnow
from app.models.email_settings import EmailSettings
from app.models.password_reset_token import PasswordResetToken
from app.models.user import User
from tests.conftest import csrf_value, login


@pytest.fixture
def sent_emails(monkeypatch):
    sent = []

    def fake_send_sync(settings, to_addr, subject, html_body):
        sent.append({"to": to_addr, "subject": subject, "html_body": html_body})

    monkeypatch.setattr(email_module, "_send_sync", fake_send_sync)
    return sent


@pytest_asyncio.fixture
async def email_enabled(session_maker):
    async with session_maker() as session:
        session.add(EmailSettings(smtp_host="smtp.test.local", from_address="noreply@test.local", enabled=True))
        await session.commit()


@pytest_asyncio.fixture
async def user_with_email(session_maker):
    async with session_maker() as session:
        u = User(username="hasmail", email="hasmail@test.local", hashed_password=hash_password("oldpassword123"))
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return u


def _extract_reset_token(html_body: str) -> str:
    match = re.search(r"/auth/reset-password/([^\s\"<]+)", html_body)
    assert match, f"Kein Reset-Link im Mail-Body gefunden: {html_body}"
    return match.group(1)


async def test_forgot_password_unknown_identifier_sends_no_email(client, email_enabled, sent_emails):
    resp = await client.post("/auth/forgot-password", data={"identifier": "does-not-exist"})
    assert resp.status_code == 200
    assert "wurde eine E-Mail" in resp.text
    assert sent_emails == []


async def test_forgot_password_known_user_can_reset_password(client, email_enabled, user_with_email, sent_emails):
    resp = await client.post("/auth/forgot-password", data={"identifier": "hasmail"})
    assert resp.status_code == 200
    assert len(sent_emails) == 1
    raw_token = _extract_reset_token(sent_emails[0]["html_body"])

    get_resp = await client.get(f"/auth/reset-password/{raw_token}")
    assert get_resp.status_code == 200
    assert "ungültig" not in get_resp.text

    post_resp = await client.post(f"/auth/reset-password/{raw_token}", data={"new_password": "newpassword456"})
    assert post_resp.status_code == 303
    assert post_resp.headers["location"].startswith("/auth/login")

    old_login = await client.post("/auth/login", data={"username": "hasmail", "password": "oldpassword123"})
    assert old_login.status_code == 401

    new_login = await client.post("/auth/login", data={"username": "hasmail", "password": "newpassword456"})
    assert new_login.status_code == 303

    # Token darf kein zweites Mal funktionieren
    reuse_resp = await client.post(f"/auth/reset-password/{raw_token}", data={"new_password": "anotherpassword789"})
    assert reuse_resp.status_code == 200
    assert "ungültig oder abgelaufen" in reuse_resp.text


async def test_reset_password_rejects_expired_token(client, session_maker, user_with_email):
    raw_token = "expired-test-token"
    async with session_maker() as session:
        session.add(
            PasswordResetToken(
                user_id=user_with_email.id,
                token_hash=hash_token(raw_token),
                expires_at=utcnow() - timedelta(hours=1),
            )
        )
        await session.commit()

    resp = await client.get(f"/auth/reset-password/{raw_token}")
    assert resp.status_code == 200
    assert "ungültig oder abgelaufen" in resp.text


async def test_create_user_with_email_succeeds_without_smtp_configured(client, session_maker, seed_data, sent_emails):
    """Kein EmailSettings-Datensatz vorhanden -> send_email liefert False,
    darf das Anlegen des Users aber nicht verhindern (nur eine Warnung)."""
    async with session_maker() as session:
        admin = User(username="admin", is_admin=True, hashed_password=hash_password("adminpass123"))
        session.add(admin)
        await session.commit()
    await login(client, "admin", "adminpass123")

    payload = {
        "username": "newmailuser",
        "password": "somepassword123",
        "first_name": "New",
        "last_name": "User",
        "barcode": "NEW-MAIL-USER",
        "home_department_id": str(seed_data["department_id"]),
        "initial_role": "nutzer",
        "email": "newuser@test.local",
        "csrf_token": csrf_value(client),
    }
    resp = await client.post("/admin/users/new", data=payload)
    assert resp.status_code == 303
    location = resp.headers["location"]
    assert location.startswith("/admin/settings?error=")
    assert location.endswith("#users")
    assert sent_emails == []
