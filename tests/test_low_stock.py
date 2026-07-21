"""Regressionstests für die tägliche Mindestbestand-Mail (app/core/low_stock.py):
sammelt Verbrauchsmaterial <= min_quantity, schickt eine Sammel-Mail an jeden
aktiven Admin mit hinterlegter E-Mail-Adresse. run_low_stock_check() nutzt
async_session_maker direkt (kein FastAPI-DI, läuft als Hintergrund-Task ohne
Request) - deshalb hier per monkeypatch auf die Test-Engine umgebogen, statt
über den client/session_maker-Fixture-Umweg.
"""
import app.core.low_stock as low_stock_module
from app.core.security import hash_password
from app.models.common import utcnow
from app.models.consumable import Consumable
from app.models.user import User


async def test_no_low_stock_sends_no_mail(session_maker, seed_data, monkeypatch):
    monkeypatch.setattr(low_stock_module, "async_session_maker", session_maker)
    sent = []
    monkeypatch.setattr(low_stock_module, "send_email", _fake_send(sent))

    async with session_maker() as session:
        session.add(Consumable(barcode="OK-1", name="Voll", quantity=50, min_quantity=5, department_id=seed_data["department_id"]))
        await session.commit()

    await low_stock_module.run_low_stock_check()
    assert sent == []


async def test_low_stock_notifies_active_admins_with_email(session_maker, seed_data, monkeypatch):
    monkeypatch.setattr(low_stock_module, "async_session_maker", session_maker)
    sent = []
    monkeypatch.setattr(low_stock_module, "send_email", _fake_send(sent))

    async with session_maker() as session:
        session.add(Consumable(barcode="LOW-1", name="Schrauben", quantity=2, min_quantity=5, department_id=seed_data["department_id"]))
        session.add(User(
            username="admin-with-mail", is_admin=True, hashed_password=hash_password("x" * 10),
            email="admin@example.test", approved_at=utcnow(),
        ))
        # Admin OHNE E-Mail - darf keine Mail bekommen (kein Empfänger vorhanden).
        session.add(User(
            username="admin-without-mail", is_admin=True, hashed_password=hash_password("x" * 10),
            approved_at=utcnow(),
        ))
        # Inaktiver Admin MIT E-Mail - darf ebenfalls nicht benachrichtigt werden.
        session.add(User(
            username="admin-inactive", is_admin=True, is_active=False, hashed_password=hash_password("x" * 10),
            email="inactive@example.test", approved_at=utcnow(),
        ))
        await session.commit()

    await low_stock_module.run_low_stock_check()
    assert sent == [("admin@example.test", "Scandy-Lite: 1 Artikel unter Mindestbestand")]


async def test_low_stock_without_any_admin_email_does_not_raise(session_maker, seed_data, monkeypatch):
    monkeypatch.setattr(low_stock_module, "async_session_maker", session_maker)
    sent = []
    monkeypatch.setattr(low_stock_module, "send_email", _fake_send(sent))

    async with session_maker() as session:
        session.add(Consumable(barcode="LOW-2", name="Muttern", quantity=0, min_quantity=5, department_id=seed_data["department_id"]))
        await session.commit()

    await low_stock_module.run_low_stock_check()  # darf nicht crashen
    assert sent == []


def _fake_send(sent_list):
    async def fake_send_email(session, to_addr, subject, html_body):
        sent_list.append((to_addr, subject))
        return True
    return fake_send_email
