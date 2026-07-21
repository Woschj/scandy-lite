#!/usr/bin/env python3
"""
Einmaliges Migrationsskript: Bestandsdaten aus der alten Scandy2-MongoDB
nach Scandy-Lite (PostgreSQL) übernehmen.

WICHTIG:
- Read-only auf MongoDB-Seite - es wird NICHTS in der alten DB verändert
  oder gelöscht.
- Standardmäßig TROCKENLAUF (--apply fehlt): zeigt nur einen Report, schreibt
  nichts. Erst mit --apply wird wirklich geschrieben.
- Idempotent: mehrfaches Ausführen mit --apply legt nichts doppelt an
  (Barcode-/Kombinations-Prüfung vor jedem Insert) - ein Abbruch mittendrin
  lässt sich also gefahrlos per erneutem Aufruf fortsetzen.
- Passwörter können NICHT migriert werden (Scandy2 nutzt Werkzeug-Hashes,
  Scandy-Lite bcrypt - unterschiedliche, nicht konvertierbare Verfahren).
  Jeder migrierte Benutzer bekommt ein zufälliges neues Passwort. Diese
  werden in eine separate Datei geschrieben (Default: migration_passwords.txt)
  - nach der Verteilung an die Nutzer UNBEDINGT LÖSCHEN.
- NICHT migriert (bewusst, siehe Scope der Original-Analyse): Tickets,
  Kantinenplan, Jobs, Custom Fields, Feature-Flags, Notification-Center.

Nutzung:
    pip install -r migrations_legacy/requirements.txt

    # 1. Erst als Trockenlauf - zeigt nur, was passieren würde:
    python -m migrations_legacy.migrate_from_mongodb \\
        --mongo-uri "mongodb://user:pass@host:27017" --mongo-db scandy

    # 2. Wenn der Report plausibel aussieht, wirklich schreiben:
    python -m migrations_legacy.migrate_from_mongodb \\
        --mongo-uri "mongodb://user:pass@host:27017" --mongo-db scandy --apply
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, create_engine  # noqa: E402

import app.models  # noqa: E402, F401  (registriert alle Tabellen in SQLModel.metadata)
from app.core.config import get_settings  # noqa: E402
from migrations_legacy.migrate_core import migrate  # noqa: E402
from migrations_legacy.transform import clean_str  # noqa: E402


def fetch_mongo_data(mongo_uri: str, mongo_db: str) -> dict:
    """Liest alle relevanten Collections roh aus MongoDB. Bewusst dünn -
    die eigentliche Logik/Validierung passiert in migrate_core.migrate()."""
    try:
        from pymongo import MongoClient
    except ImportError:
        print(
            "Fehler: pymongo ist nicht installiert. Bitte zuerst:\n"
            "  pip install -r migrations_legacy/requirements.txt",
            file=sys.stderr,
        )
        sys.exit(1)

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    try:
        client.admin.command("ping")
    except Exception as exc:
        print(f"Fehler: Konnte nicht zu MongoDB verbinden ({mongo_uri}): {exc}", file=sys.stderr)
        sys.exit(1)
    db = client[mongo_db]

    # Abteilungsnamen: primär aus settings.departments, zusätzlich als
    # Sicherheitsnetz alle tatsächlich auf Dokumenten verwendeten Werte
    # (falls die settings-Liste unvollständig/veraltet gegenüber den
    # echten Daten ist - kam im Original öfter vor).
    department_names = set()
    settings_dept_doc = db.settings.find_one({"key": "departments"})
    if settings_dept_doc and isinstance(settings_dept_doc.get("value"), list):
        department_names.update(clean_str(n) for n in settings_dept_doc["value"])
    for coll_name in ("tools", "consumables", "workers"):
        for doc in db[coll_name].find({}, {"department": 1}):
            if doc.get("department"):
                department_names.add(clean_str(doc["department"]))
    for doc in db.users.find({}, {"allowed_departments": 1, "default_department": 1}):
        for d in doc.get("allowed_departments") or []:
            department_names.add(clean_str(d))
        if doc.get("default_department"):
            department_names.add(clean_str(doc["default_department"]))
    department_names.discard("")

    # Kategorien/Standorte: department-sensitiv aus settings (siehe
    # _extract_by_department im Original) - hier roh übernommen, migrate_core
    # ordnet den einzelnen Abteilungen zu.
    def read_dept_scoped_setting(key: str) -> dict:
        doc = db.settings.find_one({"key": key})
        if not doc or "value" not in doc:
            return {}
        value = doc["value"]
        if isinstance(value, dict):
            return {clean_str(k): list(v) for k, v in value.items() if isinstance(v, list)}
        if isinstance(value, list):
            # Global/Legacy - nicht abteilungsspezifisch, allen bekannten
            # Abteilungen zuordnen (besser sichtbar als komplett verloren)
            return {name: list(value) for name in department_names}
        return {}

    categories_by_department = read_dept_scoped_setting("categories")
    locations_by_department = read_dept_scoped_setting("locations")

    return {
        "department_names": sorted(department_names),
        "categories_by_department": categories_by_department,
        "locations_by_department": locations_by_department,
        "users": list(db.users.find({})),
        "workers": list(db.workers.find({})),
        "tools": list(db.tools.find({"deleted": {"$ne": True}})),
        "consumables": list(db.consumables.find({"deleted": {"$ne": True}})),
        "lendings": list(db.lendings.find({})),
        "consumable_usages": list(db.consumable_usages.find({})),
    }


def print_report(result: dict) -> None:
    report = result["report"]
    print("\n=== Migrations-Report ===")
    for key in sorted(report):
        print(f"  {key}: {report[key]}")

    if result["warnings"]:
        print("\n=== Warnungen ===")
        for w in result["warnings"]:
            print(f"  - {w}")


def write_password_report(generated_passwords: list[tuple[str, str]], path: str) -> None:
    if not generated_passwords:
        return
    with open(path, "w") as f:
        f.write("Temporäre Passwörter für migrierte Benutzer\n")
        f.write("Bitte sicher verteilen und diese Datei danach LÖSCHEN.\n\n")
        for username, password in generated_passwords:
            f.write(f"{username}: {password}\n")
    print(f"\n{len(generated_passwords)} temporäre Passwörter geschrieben nach: {path}")
    print("WICHTIG: Datei nach Verteilung an die Nutzer löschen!")


def main() -> None:
    parser = argparse.ArgumentParser(description="Scandy2 (MongoDB) -> Scandy-Lite (PostgreSQL) Migration")
    parser.add_argument("--mongo-uri", required=True, help="z.B. mongodb://user:pass@host:27017")
    parser.add_argument("--mongo-db", required=True, help="Name der Mongo-Datenbank, z.B. 'scandy'")
    parser.add_argument("--apply", action="store_true", help="Tatsächlich schreiben (ohne diesen Schalter: nur Trockenlauf)")
    parser.add_argument("--password-report", default="migration_passwords.txt")
    args = parser.parse_args()

    print(f"Modus: {'APPLY (es wird geschrieben)' if args.apply else 'TROCKENLAUF (nichts wird geschrieben)'}")
    print(f"Lese aus MongoDB: {args.mongo_db} ...")
    data = fetch_mongo_data(args.mongo_uri, args.mongo_db)
    print(
        f"Gelesen: {len(data['tools'])} Tools, {len(data['workers'])} Workers, "
        f"{len(data['consumables'])} Consumables, {len(data['users'])} Users, "
        f"{len(data['lendings'])} Lendings, {len(data['consumable_usages'])} Consumable-Usages, "
        f"{len(data['department_names'])} Abteilungen"
    )

    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL_SYNC)

    with Session(engine) as session:
        result = migrate(session, data, apply=args.apply)

    print_report(result)

    if args.apply:
        write_password_report(result["generated_passwords"], args.password_report)
    else:
        print("\nTrockenlauf abgeschlossen - nichts wurde geschrieben.")
        print("Sieht der Report plausibel aus? Dann nochmal mit --apply ausführen.")


if __name__ == "__main__":
    main()
