"""
CSV-Export der Gegenstands-Barcodes (/items/export.csv) - gedacht für den
Massenimport in Label-Drucker-Software zum Drucken von QR-Codes. Nur für
Mitarbeiter/Admin (Massenexport ist eine Verwaltungsaktion, keine reine
Sichtbarkeits-Frage), respektiert dieselbe Abteilungs-Scoping wie die Liste,
und dieselben Filter (Suche/Kategorie/Standort/Status).
"""
import csv
import io

from app.models.common import UserRole
from app.models.department import Department
from app.models.item import Item
from app.models.user import User
from app.core.security import hash_password
from app.models.user_department_role import UserDepartmentRole
from tests.conftest import login


async def test_export_returns_csv_with_visible_items(client, session_maker, seed_data):
    async with session_maker() as session:
        session.add(Item(barcode="EXP-001", name="Akkuschrauber", category="Werkzeug", location="Regal A",
                          department_id=seed_data["department_id"]))
        session.add(Item(barcode="EXP-002", name="Bohrmaschine", department_id=seed_data["department_id"]))
        await session.commit()

    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    resp = await client.get("/items/export.csv")

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]

    # utf-8-sig statt resp.text: das Response enthält bewusst eine fuehrende
    # UTF-8-BOM (siehe items.py::export_items_csv), utf-8-sig entfernt sie
    # beim Decodieren automatisch statt sie als Teil der ersten Zelle zu lesen.
    rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
    assert rows[0] == ["barcode", "name", "kategorie", "standort", "abteilung"]
    barcodes = {row[0] for row in rows[1:]}
    assert barcodes == {"EXP-001", "EXP-002"}
    werkzeug_row = next(row for row in rows[1:] if row[0] == "EXP-001")
    assert werkzeug_row[2] == "Werkzeug"
    assert werkzeug_row[4] == "Werkstatt"


async def test_export_excludes_items_from_other_department(client, session_maker, seed_data):
    async with session_maker() as session:
        other = Department(code="other-dept", name="Andere Abteilung")
        session.add(other)
        await session.commit()
        await session.refresh(other)
        session.add(Item(barcode="EXP-OWN", name="Eigener Gegenstand", department_id=seed_data["department_id"]))
        session.add(Item(barcode="EXP-FOREIGN", name="Fremder Gegenstand", department_id=other.id))
        await session.commit()

    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    resp = await client.get("/items/export.csv")

    assert resp.status_code == 200, resp.text
    rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
    barcodes = {row[0] for row in rows[1:]}
    assert barcodes == {"EXP-OWN"}


async def test_export_respects_category_filter(client, session_maker, seed_data):
    async with session_maker() as session:
        session.add(Item(barcode="EXP-CAT-1", name="Bohrer", category="Werkzeug", department_id=seed_data["department_id"]))
        session.add(Item(barcode="EXP-CAT-2", name="Laptop", category="IT", department_id=seed_data["department_id"]))
        await session.commit()

    await login(client, seed_data["staff_username"], seed_data["staff_password"])
    resp = await client.get("/items/export.csv", params={"category": "IT"})

    rows = list(csv.reader(io.StringIO(resp.content.decode("utf-8-sig"))))
    barcodes = {row[0] for row in rows[1:]}
    assert barcodes == {"EXP-CAT-2"}


async def test_export_blocked_for_pure_nutzer_role(client, session_maker, seed_data):
    async with session_maker() as session:
        nutzer = User(
            username="nutzer1", is_admin=False, hashed_password=hash_password("nutzerpass123"),
            barcode="W-NUTZER", department_id=seed_data["department_id"],
        )
        session.add(nutzer)
        await session.commit()
        await session.refresh(nutzer)
        session.add(UserDepartmentRole(user_id=nutzer.id, department_id=seed_data["department_id"], role=UserRole.NUTZER))
        await session.commit()

    await login(client, "nutzer1", "nutzerpass123")
    resp = await client.get("/items/export.csv")

    assert resp.status_code == 403, resp.text
