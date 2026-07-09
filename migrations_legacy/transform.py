"""
Reine Transformations-Funktionen: Mongo-Dokument (dict) -> Scandy-Lite-Felder.

Bewusst ohne jeden DB-Zugriff in diesem Modul - macht die eigentliche
Übersetzungslogik isoliert testbar (siehe tests/test_transform.py), unabhängig
von einer laufenden MongoDB/Postgres-Instanz.
"""
import re
import secrets
import string
import unicodedata
from datetime import datetime

from app.models.common import ItemStatus, UserRole

# Rollen-Zuordnung Scandy2 -> Scandy-Lite. 'teilnehmer' (Kursteilnehmer mit
# Ablaufdatum) passt inhaltlich am ehesten zu unserer Rolle 'Nutzer'
# (ansehen + reservieren, keine Verwaltung).
ROLE_MAP = {
    "admin": UserRole.ADMIN,
    "anwender": UserRole.MITARBEITER,
    "mitarbeiter": UserRole.MITARBEITER,
    "teilnehmer": UserRole.NUTZER,
}

# Status-Zuordnung. 'ausgeliehen' bewusst NICHT übernommen - der tatsächliche
# Status wird beim Import aus den offenen Lendings neu abgeleitet, weil das
# Original selbst Funktionen zur Reparatur von Tool-Status/Lending-
# Inkonsistenzen hatte (validate_lending_consistency /
# fix_lending_inconsistencies) - der gespeicherte String ist also nicht
# unbedingt vertrauenswürdig.
STATUS_MAP = {
    "verfügbar": ItemStatus.VERFUEGBAR,
    "verfuegbar": ItemStatus.VERFUEGBAR,
    "defekt": ItemStatus.DEFEKT,
    "ausgemustert": ItemStatus.AUSGEMUSTERT,
}

_UMLAUT_MAP = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "AE", "Ö": "OE", "Ü": "UE",
}


def slugify_department_code(name: str) -> str:
    """'Werkstatt Elektro' -> 'werkstatt_elektro'. Deterministisch, damit
    derselbe Abteilungsname bei jedem Lauf denselben Code ergibt (wichtig für
    Idempotenz - sonst entstehen bei jedem erneuten Lauf neue Duplikate)."""
    if not name:
        return "unbekannt"
    replaced = "".join(_UMLAUT_MAP.get(ch, ch) for ch in name)
    normalized = unicodedata.normalize("NFKD", replaced).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "_", normalized.lower()).strip("_")
    return (slug or "unbekannt")[:50]


def map_user_role(mongo_role: str | None) -> UserRole:
    return ROLE_MAP.get((mongo_role or "").lower(), UserRole.NUTZER)


def map_item_status(mongo_status: str | None) -> ItemStatus:
    return STATUS_MAP.get((mongo_status or "").lower(), ItemStatus.VERFUEGBAR)


def generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(14))


def clean_str(value, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def to_datetime(value) -> datetime | None:
    """Mongo liefert bereits datetime-Objekte (BSON) - dieser Helfer fängt
    nur den Fall ab, dass irgendwo doch ein String/None durchrutscht."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                return datetime.strptime(value, fmt)
            except ValueError:
                continue
    return None


def build_item_kwargs(tool_doc: dict, department_id) -> dict:
    return {
        "barcode": clean_str(tool_doc.get("barcode")),
        "name": clean_str(tool_doc.get("name")) or "(ohne Namen)",
        "category": clean_str(tool_doc.get("category")) or None,
        "location": clean_str(tool_doc.get("location")) or None,
        "notes": clean_str(tool_doc.get("description")) or None,
        "status": map_item_status(tool_doc.get("status")),
        "department_id": department_id,
    }


def build_consumable_kwargs(consumable_doc: dict, department_id) -> dict:
    try:
        quantity = int(consumable_doc.get("quantity", 0) or 0)
    except (TypeError, ValueError):
        quantity = 0
    try:
        min_quantity = int(consumable_doc.get("min_quantity", 0) or 0)
    except (TypeError, ValueError):
        min_quantity = 0
    return {
        "barcode": clean_str(consumable_doc.get("barcode")),
        "name": clean_str(consumable_doc.get("name")) or "(ohne Namen)",
        "category": clean_str(consumable_doc.get("category")) or None,
        "location": clean_str(consumable_doc.get("location")) or None,
        "notes": clean_str(consumable_doc.get("description")) or None,
        "unit": "Stück",  # gab es im Original nicht - einziger sinnvoller Default
        "quantity": max(quantity, 0),
        "min_quantity": max(min_quantity, 0),
        "department_id": department_id,
    }


def build_worker_kwargs(worker_doc: dict, department_id) -> dict:
    return {
        "barcode": clean_str(worker_doc.get("barcode")) or f"MIGRATED-{secrets.token_hex(4)}",
        "first_name": clean_str(worker_doc.get("firstname")) or "?",
        "last_name": clean_str(worker_doc.get("lastname")) or "?",
        "department_id": department_id,
        "is_active": not worker_doc.get("deleted", False),
    }


def build_user_kwargs(user_doc: dict, department_id, hashed_password: str) -> dict:
    return {
        "username": clean_str(user_doc.get("username")),
        "role": map_user_role(user_doc.get("role")),
        "hashed_password": hashed_password,
        "department_id": department_id,
        "is_active": user_doc.get("is_active", True) is not False,
    }


def is_real_withdrawal(usage_doc: dict) -> bool:
    """Nur tatsächliche Entnahmen durch einen echten Mitarbeiter migrieren
    (negative Menge, kein Platzhalter-'admin'-Kürzel als Worker) - Nachschub-
    Buchungen haben in Scandy-Lite kein Historien-Äquivalent (dort einfach
    eine direkte Bestandsanpassung ohne Log)."""
    try:
        qty = float(usage_doc.get("quantity", 0) or 0)
    except (TypeError, ValueError):
        return False
    worker_barcode = clean_str(usage_doc.get("worker_barcode"))
    return qty < 0 and bool(worker_barcode) and worker_barcode.lower() != "admin"
