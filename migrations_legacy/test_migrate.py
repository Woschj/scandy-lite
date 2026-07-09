"""
Testet migrate_core.migrate() mit synthetischen Mongo-Dokumenten gegen eine
echte (SQLite-)Datenbank - kein Mongo, aber ein echter End-to-End-Durchlauf
der kompletten Schreiblogik inkl. Referenz-Auflösung, Duplikat-Erkennung,
Status-Ableitung aus offenen Ausleihen.
"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, SQLModel, create_engine, select  # noqa: E402

import app.models  # noqa: E402  (registriert alle Tabellen)
from app.models.common import ItemStatus  # noqa: E402
from app.models.consumable import Consumable, ConsumableUsage  # noqa: E402
from app.models.department import Department  # noqa: E402
from app.models.item import Item  # noqa: E402
from app.models.lending import Lending  # noqa: E402
from app.models.preset import Category, Location  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.worker import Worker  # noqa: E402
from migrations_legacy.migrate_core import migrate  # noqa: E402


def check(label, cond):
    print(("OK  " if cond else "FEHLER"), label)


def build_sample_data():
    now = datetime.now()
    return {
        "department_names": ["Werkstatt", "Büro"],
        "categories_by_department": {"Werkstatt": ["Elektrowerkzeug", "Handwerkzeug"]},
        "locations_by_department": {"Werkstatt": ["Regal A1"]},
        "users": [
            {"username": "mmuster", "role": "anwender", "default_department": "Werkstatt", "is_active": True},
            {"username": "erika", "role": "teilnehmer", "default_department": "Werkstatt", "is_active": True},
            {"username": "", "role": "admin"},  # kaputt: kein Username -> muss übersprungen werden
        ],
        "workers": [
            {"barcode": "W-001", "firstname": "Max", "lastname": "Muster", "department": "Werkstatt", "username": "mmuster", "deleted": False},
            {"barcode": "W-002", "firstname": "Erika", "lastname": "Student", "department": "Werkstatt", "username": "erika", "deleted": False},
            {"barcode": "W-999", "firstname": "Verwaist", "lastname": "Worker", "department": "GhostDept", "deleted": False},  # unbekannte Abteilung
        ],
        "tools": [
            {"barcode": "T-001", "name": "Akkuschrauber", "category": "Elektrowerkzeug", "location": "Regal A1", "status": "verfügbar", "department": "Werkstatt"},
            {"barcode": "T-002", "name": "Bohrmaschine", "status": "verfügbar", "department": "Werkstatt"},
            {"barcode": "T-003", "name": "Verwaistes Tool", "department": "GhostDept"},  # unbekannte Abteilung -> skip
            {"barcode": "", "name": "Ohne Barcode", "department": "Werkstatt"},  # kein Barcode -> skip
        ],
        "consumables": [
            {"barcode": "C-001", "name": "Schrauben 4x40", "quantity": "100", "min_quantity": "10", "department": "Werkstatt"},
        ],
        "lendings": [
            # T-002 ist noch offen ausgeliehen (kein returned_at) -> Item-Status muss AUSGELIEHEN werden
            {"tool_barcode": "T-002", "worker_barcode": "W-001", "lent_at": now - timedelta(days=2), "returned_at": None, "department": "Werkstatt"},
            # T-001 wurde ausgeliehen und zurückgegeben -> nur Historie, Status bleibt verfügbar
            {"tool_barcode": "T-001", "worker_barcode": "W-002", "lent_at": now - timedelta(days=10), "returned_at": now - timedelta(days=9), "department": "Werkstatt"},
            # Kaputte Referenz: unbekannter Worker-Barcode -> muss übersprungen werden
            {"tool_barcode": "T-001", "worker_barcode": "W-NICHT-VORHANDEN", "lent_at": now, "returned_at": None, "department": "Werkstatt"},
        ],
        "consumable_usages": [
            # Echte Entnahme -> migrieren
            {"consumable_barcode": "C-001", "worker_barcode": "W-001", "quantity": -15, "used_at": now - timedelta(days=1)},
            # Nachschub (positiv) -> NICHT migrieren
            {"consumable_barcode": "C-001", "worker_barcode": "admin", "quantity": 50, "used_at": now - timedelta(days=5)},
            # Admin-Korrektur (negativ, aber worker='admin') -> NICHT migrieren
            {"consumable_barcode": "C-001", "worker_barcode": "admin", "quantity": -5, "used_at": now - timedelta(days=3)},
        ],
    }


def run():
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)

    data = build_sample_data()

    with Session(engine) as session:
        # --- 1) Dry-Run: darf NICHTS in die DB schreiben ---
        result = migrate(session, data, apply=False)
        session.rollback()
        check("Dry-Run: keine Abteilungen geschrieben", session.exec(select(Department)).all() == [])
        check("Dry-Run: keine Items geschrieben", session.exec(select(Item)).all() == [])
        check("Dry-Run: Report zeigt trotzdem geplante Anzahl Items", result["report"].get("items_created") == 2)
        check("Dry-Run: Report zeigt geplante Departments (2)", result["report"].get("departments_created") == 2)

    with Session(engine) as session:
        # --- 2) Echter Lauf ---
        result = migrate(session, data, apply=True)
        report = result["report"]

        check("2 Abteilungen angelegt (Werkstatt, Büro)", report.get("departments_created") == 2)
        check("2 Kategorien angelegt", report.get("categories_created") == 2)
        check("1 Standort angelegt", report.get("locations_created") == 1)

        check("2 gültige User angelegt (mmuster, erika)", report.get("users_created") == 2)
        check("Kaputter User (kein Username) wurde übersprungen, kein Crash", "users_created" in report)

        check("2 gültige Worker angelegt", report.get("workers_created") == 2)
        check("1 Worker mit unbekannter Abteilung übersprungen", report.get("workers_skipped_no_department") == 1)

        check("2 gültige Items angelegt", report.get("items_created") == 2)
        check("1 Item mit unbekannter Abteilung übersprungen", report.get("items_skipped_no_department") == 1)
        check("1 Item ohne Barcode übersprungen", report.get("items_skipped_no_barcode") == 1)

        check("1 Consumable angelegt", report.get("consumables_created") == 1)

        check("2 gültige Lendings angelegt (1 offen, 1 abgeschlossen)", report.get("lendings_created") == 2)
        check("1 Lending mit kaputter Worker-Referenz übersprungen", report.get("lendings_skipped_broken_reference") == 1)

        check("Nur 1 echte Entnahme migriert (Nachschub + Admin-Korrektur ausgeschlossen)",
              report.get("consumable_usages_created") == 1)
        check("2 Consumable-Usages als 'keine Entnahme' korrekt aussortiert",
              report.get("consumable_usages_skipped_not_withdrawal") == 2)

        check("2 temporäre Passwörter generiert (für mmuster + erika)", len(result["generated_passwords"]) == 2)
        usernames_with_pw = {u for u, _ in result["generated_passwords"]}
        check("Passwörter für die richtigen User", usernames_with_pw == {"mmuster", "erika"})

        # --- Inhaltliche Detailprüfungen direkt in der DB ---
        session.commit()

        item_t002 = session.exec(select(Item).where(Item.barcode == "T-002")).first()
        check("T-002 (offene Ausleihe) hat Status AUSGELIEHEN nach Migration",
              item_t002 is not None and item_t002.status == ItemStatus.AUSGELIEHEN)

        item_t001 = session.exec(select(Item).where(Item.barcode == "T-001")).first()
        check("T-001 (abgeschlossene Ausleihe) hat weiterhin Status VERFUEGBAR",
              item_t001 is not None and item_t001.status == ItemStatus.VERFUEGBAR)

        erika_user = session.exec(select(User).where(User.username == "erika")).first()
        check("erika bekam Rolle NUTZER (aus 'teilnehmer' gemappt)",
              erika_user is not None and erika_user.role.value == "nutzer")

        erika_worker = session.exec(select(Worker).where(Worker.barcode == "W-002")).first()
        check("Worker 'erika' ist mit dem User-Login verknüpft",
              erika_worker is not None and erika_user is not None and erika_worker.user_id == erika_user.id)

        usage = session.exec(select(ConsumableUsage)).first()
        check("Migrierte Entnahme hat positive Menge (15, nicht -15)", usage is not None and usage.quantity == 15)

        lendings_all = session.exec(select(Lending)).all()
        check("Genau 2 Lendings in der DB", len(lendings_all) == 2)

    # --- 3) Idempotenz: zweiter Lauf mit denselben Daten darf NICHTS doppelt anlegen ---
    with Session(engine) as session:
        result2 = migrate(session, data, apply=True)
        report2 = result2["report"]
        check("2. Lauf: keine neuen Abteilungen", report2.get("departments_created", 0) == 0)
        check("2. Lauf: Items als 'existiert bereits' erkannt", report2.get("items_skipped_existing") == 2)
        check("2. Lauf: Worker als 'existiert bereits' erkannt", report2.get("workers_skipped_existing") == 2)
        check("2. Lauf: User als 'existiert bereits' erkannt", report2.get("users_skipped_existing") == 2)

        session.commit()
        all_items = session.exec(select(Item)).all()
        check("Nach 2 Läufen immer noch nur 2 Items (keine Duplikate)", len(all_items) == 2)
        all_lendings = session.exec(select(Lending)).all()
        check("Nach 2 Läufen immer noch nur 2 Lendings (Duplikat-Schutz über item+worker+lent_at)",
              len(all_lendings) == 2)
        check("2. Lauf: Lendings als 'existiert bereits' erkannt", report2.get("lendings_skipped_existing") == 2)
        all_usages = session.exec(select(ConsumableUsage)).all()
        check("Nach 2 Läufen immer noch nur 1 ConsumableUsage (keine Duplikate)", len(all_usages) == 1)


run()
print("\nAlle Migrations-Tests durchgelaufen.")
