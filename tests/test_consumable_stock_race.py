"""
Regressionstest für den Race-Condition-Fix bei Verbrauchsmaterial-Bestand
(siehe app/routers/scan.py scan_consume, app/routers/consumables.py
adjust_consumable): zwei gleichzeitige Entnahmen dürfen den Bestand
zusammen nie unter 0 drücken, selbst wenn beide Anfragen einzeln betrachtet
"passen" würden.
"""
import asyncio

from tests.conftest import csrf_value, login

from app.models.consumable import Consumable
from app.models.user import User


async def test_concurrent_consume_never_oversells_stock(client, session_maker, seed_data):
    department_id = seed_data["department_id"]

    async with session_maker() as session:
        consumable = Consumable(barcode="C-RACE", name="Schrauben", quantity=5, department_id=department_id)
        worker = User(username="race-worker", barcode="W-RACE", first_name="Race", last_name="Worker", department_id=department_id)
        session.add(consumable)
        session.add(worker)
        await session.commit()
        await session.refresh(consumable)
        await session.refresh(worker)
        consumable_id = consumable.id
        worker_barcode = worker.barcode

    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    token = csrf_value(client)

    async def consume() -> bool:
        """True = Entnahme erfolgreich (Redirect auf ?ok=...)."""
        resp = await client.post(
            "/scan/consume",
            data={
                "consumable_id": str(consumable_id),
                "quantity": "3",
                "worker_barcode": worker_barcode,
                "csrf_token": token,
            },
        )
        assert resp.status_code == 303
        location = resp.headers["location"]
        assert "ok=" in location or "error=" in location
        return "ok=" in location

    # Bestand ist 5, zwei Entnahmen von je 3 angefragt - zusammen 6, mehr als
    # vorhanden. Ohne den atomaren UPDATE-Guard könnten (je nach Timing)
    # beide "erfolgreich" sein und der Bestand würde negativ.
    results = await asyncio.gather(consume(), consume())
    assert results.count(True) == 1, f"Erwartet genau eine erfolgreiche Entnahme, bekommen: {results}"

    async with session_maker() as session:
        refreshed = await session.get(Consumable, consumable_id)
        assert refreshed.quantity == 2
        assert refreshed.quantity >= 0
