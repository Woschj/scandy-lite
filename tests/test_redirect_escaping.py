"""
Regressionstest für app.core.responses.redirect_with_query: Namen mit
URL-Sonderzeichen (&, #, %) dürfen die Query-String-Struktur der
Redirect-Location nicht brechen (siehe Fund in app/routers/scan.py,
reservations.py, pickup.py - Namen wurden vorher unescaped per f-String in
die Redirect-URL eingesetzt).
"""
from urllib.parse import parse_qs, urlsplit

from tests.conftest import csrf_value, login

from app.models.item import Item
from app.models.user import User


async def test_lend_redirect_escapes_special_characters_in_names(client, session_maker, seed_data):
    department_id = seed_data["department_id"]

    async with session_maker() as session:
        # "&" und "#" sind die kritischen Zeichen: brechen eine naive
        # f-String-Query ("?ok=X&Y" wird sonst als zwei Parameter gelesen).
        item = Item(barcode="I-ESC", name="Akkuschrauber & Bits #1", department_id=department_id)
        worker = User(username="esc-worker", barcode="W-ESC", first_name="Anna", last_name="Müller & Schmidt", department_id=department_id)
        session.add(item)
        session.add(worker)
        await session.commit()
        await session.refresh(item)
        await session.refresh(worker)
        item_id = item.id
        worker_barcode = worker.barcode
        expected_message = f"{item.name} an {worker.full_name} ausgeliehen."

    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    token = csrf_value(client)

    resp = await client.post(
        "/scan/lend",
        data={
            "item_id": str(item_id),
            "worker_barcode": worker_barcode,
            "signature": "data:image/png;base64,AAAA",
            "csrf_token": token,
        },
    )
    assert resp.status_code == 303
    location = resp.headers["location"]

    # Der kritische Teil: die Query-Struktur muss trotz "&"/"#" im Namen
    # gültig bleiben - genau EIN Parameter "ok" mit dem vollen, unversehrten Text.
    parsed = urlsplit(location)
    query = parse_qs(parsed.query)
    assert list(query.keys()) == ["ok"]
    assert query["ok"] == [expected_message]

    # Und die Fehlermeldung kommt unverändert im gerenderten HTML an (Jinja
    # escaped nur für HTML, nicht die Botschaft selbst).
    follow_up = await client.get(location)
    assert follow_up.status_code == 200
    assert "Akkuschrauber &amp; Bits #1" in follow_up.text or "Akkuschrauber & Bits #1" in follow_up.text
