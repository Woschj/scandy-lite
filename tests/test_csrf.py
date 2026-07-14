"""
Regressionstest für den CSRF-Schutz (app.core.deps.verify_csrf): mutierende
POST-Routen müssen ein zum Session-Cookie passendes csrf_token-Feld verlangen;
Login selbst (vor dem Einloggen gibt es noch kein Session-Cookie) bleibt bewusst
ausgenommen.
"""
from tests.conftest import csrf_value, login


def _create_item_payload(department_id, barcode: str) -> dict:
    return {
        "department_id": str(department_id),
        "barcode": barcode,
        "name": "Neuer Gegenstand",
        "category": "",
        "location": "",
        "notes": "",
    }


async def test_post_without_csrf_token_is_rejected(client, seed_data):
    await login(client, seed_data["staff_username"], seed_data["staff_password"])

    resp = await client.post("/items/new", data=_create_item_payload(seed_data["department_id"], "NO-CSRF"))
    assert resp.status_code == 403


async def test_post_with_wrong_csrf_token_is_rejected(client, seed_data):
    await login(client, seed_data["staff_username"], seed_data["staff_password"])

    payload = _create_item_payload(seed_data["department_id"], "WRONG-CSRF")
    payload["csrf_token"] = "definitely-not-valid"
    resp = await client.post("/items/new", data=payload)
    assert resp.status_code == 403


async def test_post_with_valid_csrf_token_succeeds(client, seed_data):
    await login(client, seed_data["staff_username"], seed_data["staff_password"])

    payload = _create_item_payload(seed_data["department_id"], "VALID-CSRF")
    payload["csrf_token"] = csrf_value(client)
    resp = await client.post("/items/new", data=payload)
    assert resp.status_code == 303
    assert resp.headers["location"] == "/items"


async def test_login_does_not_require_csrf_token(client, seed_data):
    resp = await client.post(
        "/auth/login",
        data={"username": seed_data["staff_username"], "password": seed_data["staff_password"]},
    )
    assert resp.status_code == 303
