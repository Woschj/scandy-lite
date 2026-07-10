"""
Liest ein Scandy2-eigenes Backup (ZIP aus dem "Backup erstellen"-Menü, oder
die darin enthaltene JSON-Datei direkt) und übersetzt es in das Format, das
migrations_legacy/migrate_core.py::migrate() erwartet.

WICHTIGE EINSCHRÄNKUNG: Scandy2s eigenes Backup exportiert die
'users'-Collection bewusst NIE (Sicherheitsentscheidung im Original-Code,
sowohl beim mongodump- als auch beim JSON-Fallback-Pfad - siehe
app/utils/unified_backup_manager.py im Scandy2-Quellcode). Über diesen Weg
importierte Daten enthalten deshalb IMMER Gegenstände/Material/Mitarbeiter-
Ausweise/Historie, aber NIE Benutzer-Logins - die müssen nach dem Import
manuell in Scandy-Lite angelegt und den migrierten Mitarbeiter-Ausweisen
zugeordnet werden.

Format der JSON-Datei (von Scandy2 selbst per bson.json_util.dumps erzeugt):
    {
        "metadata": {...},
        "data": {
            "tools": [...], "workers": [...], "consumables": [...],
            "lendings": [...], "consumable_usages": [...], "settings": [...],
            ... (weitere, für uns irrelevante Collections wie tickets, jobs, ...)
        }
    }
"""
import io
import json
import zipfile

from bson import json_util


class ImportParseError(Exception):
    """Datei konnte nicht als Scandy2-Backup erkannt/gelesen werden."""


def _find_backup_json_in_zip(zip_bytes: bytes) -> dict:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        candidates = [
            name for name in zf.namelist()
            if name.startswith("mongodb/") and name.endswith(".json")
        ]
        if not candidates:
            # Fallback: irgendeine JSON-Datei auf oberster Ebene, die nicht
            # offensichtlich Metadaten ist (falls die Ordnerstruktur mal abweicht)
            candidates = [
                name for name in zf.namelist()
                if name.endswith(".json")
                and "backup_metadata" not in name
                and "checksums" not in name
                and "/" not in name.strip("/")
            ]
        if not candidates:
            raise ImportParseError(
                "In der ZIP-Datei wurde keine Backup-JSON gefunden. Erwartet wird "
                "eine Datei unter 'mongodb/*.json' - so wie sie Scandy2s eigenes "
                "'Backup erstellen' erzeugt (ohne mongodump im Container läuft das "
                "automatisch über diesen Pfad)."
            )
        with zf.open(candidates[0]) as f:
            raw = f.read()
    return json_util.loads(raw)


def parse_scandy2_export(filename: str, raw_bytes: bytes) -> dict:
    """
    Nimmt die rohen Bytes einer hochgeladenen Datei (.zip oder .json) entgegen
    und gibt das 'data'-dict zurück, wie es migrate_core.migrate() erwartet.
    Wirft ImportParseError mit einer für Admins verständlichen Meldung, wenn
    die Datei nicht dem erwarteten Scandy2-Backup-Format entspricht.
    """
    lower_name = filename.lower()
    try:
        if lower_name.endswith(".zip"):
            backup = _find_backup_json_in_zip(raw_bytes)
        elif lower_name.endswith(".json"):
            backup = json_util.loads(raw_bytes)
        else:
            raise ImportParseError(
                f"Unbekanntes Dateiformat '{filename}' - bitte das ZIP aus Scandy2s "
                "'Backup erstellen' hochladen (oder die darin enthaltene .json-Datei direkt)."
            )
    except ImportParseError:
        raise
    except (json.JSONDecodeError, zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise ImportParseError(f"Datei konnte nicht gelesen werden - ist es wirklich ein Scandy2-Backup? ({exc})") from exc

    if not isinstance(backup, dict) or "data" not in backup:
        raise ImportParseError(
            "Die Datei sieht nicht wie ein Scandy2-Backup aus (erwartet: ein "
            "JSON-Objekt mit einem 'data'-Feld). Bitte das Original-Backup-ZIP "
            "verwenden, nicht selbst zusammengestellte Dateien."
        )

    mongo_data = backup["data"]
    if not isinstance(mongo_data, dict):
        raise ImportParseError("Unerwartetes Format im 'data'-Feld der Backup-Datei.")

    tools = mongo_data.get("tools", []) or []
    workers = mongo_data.get("workers", []) or []
    consumables = mongo_data.get("consumables", []) or []
    lendings = mongo_data.get("lendings", []) or []
    consumable_usages = mongo_data.get("consumable_usages", []) or []
    settings_docs = mongo_data.get("settings", []) or []

    # Nur nicht-gelöschte Datensätze übernehmen (Scandy2 exportiert auch
    # soft-gelöschte Einträge mit - unsere migrate_core-Logik filtert das
    # selbst nicht, das muss hier passieren, weil wir keine Live-Query mehr
    # haben wie das CLI-Skript, das direkt gegen Mongo filtert).
    tools = [t for t in tools if not t.get("deleted")]
    consumables = [c for c in consumables if not c.get("deleted")]
    workers = [w for w in workers if not w.get("deleted")]

    department_names = set()
    categories_by_department: dict = {}
    locations_by_department: dict = {}

    for doc in settings_docs:
        key = doc.get("key")
        value = doc.get("value")
        if key == "departments" and isinstance(value, list):
            department_names.update(str(v).strip() for v in value if v)
        elif key == "categories" and isinstance(value, dict):
            categories_by_department = value
        elif key == "locations" and isinstance(value, dict):
            locations_by_department = value

    # Sicherheitsnetz: falls die departments-Liste in den settings unvollständig
    # ist, zusätzlich alle tatsächlich auf Dokumenten verwendeten Werte sammeln
    # (gleiches Vorgehen wie im CLI-Migrationsskript).
    for doc in tools + consumables + workers:
        dept = doc.get("department")
        if dept:
            department_names.add(str(dept).strip())
    department_names.discard("")

    return {
        "department_names": sorted(department_names),
        "categories_by_department": categories_by_department,
        "locations_by_department": locations_by_department,
        "users": [],  # Scandy2-Backups enthalten NIE Benutzer - siehe Modul-Docstring
        "workers": workers,
        "tools": tools,
        "consumables": consumables,
        "lendings": lendings,
        "consumable_usages": consumable_usages,
    }
