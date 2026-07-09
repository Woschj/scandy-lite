"""
Testet fetch_mongo_data() (die pymongo-Leseschicht) gegen mongomock -
eine In-Memory-Nachbildung von MongoDB. Kein echter Server nötig, aber ein
echter pymongo-Query-Pfad (im Gegensatz zu migrate_core, das mit bereits
gelesenen Python-dicts arbeitet).
"""
import sys
from datetime import datetime
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mongomock  # noqa: E402


def check(label, cond):
    print(("OK  " if cond else "FEHLER"), label)


def run():
    client = mongomock.MongoClient()
    db = client["scandy_test"]

    # Realistische Testdaten, wie sie in der echten Scandy2-Struktur vorkommen
    db.settings.insert_one({"key": "departments", "value": ["Werkstatt", "Büro"]})
    db.settings.insert_one({"key": "categories", "value": {"Werkstatt": ["Elektrowerkzeug"]}})
    db.settings.insert_one({"key": "locations", "value": {"Werkstatt": ["Regal A1"]}})

    db.tools.insert_one({
        "barcode": "T-001", "name": "Akkuschrauber", "category": "Elektrowerkzeug",
        "department": "Werkstatt", "status": "verfügbar", "deleted": False,
    })
    db.tools.insert_one({
        "barcode": "T-DELETED", "name": "Gelöschtes Tool", "department": "Werkstatt", "deleted": True,
    })
    db.workers.insert_one({
        "barcode": "W-001", "firstname": "Max", "lastname": "Muster", "department": "Werkstatt",
        "username": "mmuster", "deleted": False,
    })
    db.consumables.insert_one({
        "barcode": "C-001", "name": "Schrauben", "department": "Werkstatt", "quantity": 50, "deleted": False,
    })
    db.users.insert_one({
        "username": "mmuster", "role": "anwender", "default_department": "Werkstatt", "is_active": True,
    })
    db.lendings.insert_one({
        "tool_barcode": "T-001", "worker_barcode": "W-001", "lent_at": datetime.now(), "returned_at": None,
    })
    db.consumable_usages.insert_one({
        "consumable_barcode": "C-001", "worker_barcode": "W-001", "quantity": -5, "used_at": datetime.now(),
    })

    # MongoClient(...) im Skript durch den mongomock-Client umleiten
    with mock.patch("pymongo.MongoClient", return_value=client):
        from migrations_legacy.migrate_from_mongodb import fetch_mongo_data
        data = fetch_mongo_data("mongodb://fake", "scandy_test")

    check("Abteilungen korrekt gelesen (aus settings)", set(data["department_names"]) == {"Werkstatt", "Büro"})
    check("Nur nicht-gelöschte Tools gelesen (1, nicht 2)", len(data["tools"]) == 1)
    check("Tool-Inhalt korrekt", data["tools"][0]["barcode"] == "T-001")
    check("Workers gelesen", len(data["workers"]) == 1)
    check("Consumables gelesen", len(data["consumables"]) == 1)
    check("Users gelesen", len(data["users"]) == 1)
    check("Lendings gelesen", len(data["lendings"]) == 1)
    check("Consumable-Usages gelesen", len(data["consumable_usages"]) == 1)
    check("Kategorien department-scoped korrekt extrahiert",
          data["categories_by_department"].get("Werkstatt") == ["Elektrowerkzeug"])
    check("Standorte department-scoped korrekt extrahiert",
          data["locations_by_department"].get("Werkstatt") == ["Regal A1"])

    # Die gelesenen Daten müssen 1:1 in migrate_core.migrate() einspeisbar sein
    from sqlmodel import Session, SQLModel, create_engine
    import app.models  # noqa: F401
    from migrations_legacy.migrate_core import migrate

    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        result = migrate(session, data, apply=True)
    check("End-to-End (Mongo-Lesen -> Migrations-Logik) läuft ohne Fehler durch",
          result["report"].get("items_created") == 1 and result["report"].get("workers_created") == 1)


run()
print("\nAlle Mongo-Lese-Tests durchgelaufen.")
