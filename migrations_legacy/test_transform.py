"""Unit-Tests für migrations_legacy/transform.py - keine DB, kein Mongo nötig."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from migrations_legacy.transform import (  # noqa: E402
    build_consumable_kwargs,
    build_item_kwargs,
    build_user_kwargs,
    build_worker_kwargs,
    is_real_withdrawal,
    map_item_status,
    map_user_role,
    slugify_department_code,
)
from app.models.common import ItemStatus, UserRole  # noqa: E402


def check(label, cond):
    print(("OK  " if cond else "FEHLER"), label)


# --- slugify_department_code ---
check("Umlaute korrekt transkribiert", slugify_department_code("Büro & Verwaltung") == "buero_verwaltung")
check("Leerzeichen -> Unterstrich", slugify_department_code("IT Service") == "it_service")
check("Deterministisch (gleicher Input -> gleicher Output)",
      slugify_department_code("Werkstatt") == slugify_department_code("Werkstatt"))
check("Leerer Name -> Fallback", slugify_department_code("") == "unbekannt")
check("Nur Sonderzeichen -> Fallback", slugify_department_code("!!!") == "unbekannt")

# --- map_user_role ---
check("admin -> ADMIN", map_user_role("admin") == UserRole.ADMIN)
check("anwender -> MITARBEITER", map_user_role("anwender") == UserRole.MITARBEITER)
check("teilnehmer -> NUTZER", map_user_role("teilnehmer") == UserRole.NUTZER)
check("Unbekannte Rolle -> NUTZER (sicherer Default, nicht Admin!)", map_user_role("irgendwas") == UserRole.NUTZER)
check("None -> NUTZER ohne Crash", map_user_role(None) == UserRole.NUTZER)

# --- map_item_status ---
check("verfügbar (Umlaut) -> VERFUEGBAR", map_item_status("verfügbar") == ItemStatus.VERFUEGBAR)
check("defekt -> DEFEKT", map_item_status("defekt") == ItemStatus.DEFEKT)
check("ausgeliehen -> NICHT direkt übernommen (Default verfügbar)", map_item_status("ausgeliehen") == ItemStatus.VERFUEGBAR)
check("Unbekannt -> VERFUEGBAR", map_item_status("murks") == ItemStatus.VERFUEGBAR)

# --- build_item_kwargs ---
dept_id = "dept-123"
tool_doc = {
    "barcode": " T-001 ", "name": "Akkuschrauber", "category": "Elektrowerkzeug",
    "location": "Regal A1", "description": "Mit Ladegerät", "status": "defekt",
}
kw = build_item_kwargs(tool_doc, dept_id)
check("Item: Barcode getrimmt", kw["barcode"] == "T-001")
check("Item: Name übernommen", kw["name"] == "Akkuschrauber")
check("Item: Status korrekt gemappt", kw["status"] == ItemStatus.DEFEKT)
check("Item: department_id gesetzt", kw["department_id"] == dept_id)

empty_tool = {"barcode": "T-002"}
kw2 = build_item_kwargs(empty_tool, dept_id)
check("Item ohne Namen -> Fallback statt Crash", kw2["name"] == "(ohne Namen)")
check("Item ohne Kategorie -> None statt leerer String", kw2["category"] is None)

# --- build_consumable_kwargs ---
cons_doc = {"barcode": "C-001", "name": "Schrauben", "quantity": "50", "min_quantity": "5"}
kw3 = build_consumable_kwargs(cons_doc, dept_id)
check("Consumable: Menge als int übernommen", kw3["quantity"] == 50)
check("Consumable: Einheit defaultet auf Stück (gab's im Original nicht)", kw3["unit"] == "Stück")

bad_cons = {"barcode": "C-002", "quantity": "kaputt", "min_quantity": None}
kw4 = build_consumable_kwargs(bad_cons, dept_id)
check("Consumable: Kaputte Menge -> 0 statt Crash", kw4["quantity"] == 0)

# --- build_worker_kwargs ---
worker_doc = {"barcode": "W-001", "firstname": "Max", "lastname": "Muster", "deleted": False}
kw5 = build_worker_kwargs(worker_doc, dept_id)
check("Worker: Felder korrekt übernommen", kw5["first_name"] == "Max" and kw5["last_name"] == "Muster")
check("Worker: is_active aus 'deleted' abgeleitet", kw5["is_active"] is True)

deleted_worker = {"barcode": "W-002", "firstname": "Tom", "lastname": "Test", "deleted": True}
kw6 = build_worker_kwargs(deleted_worker, dept_id)
check("Worker: gelöscht im Original -> is_active False", kw6["is_active"] is False)

worker_no_barcode = {"firstname": "Ohne", "lastname": "Barcode"}
kw7 = build_worker_kwargs(worker_no_barcode, dept_id)
check("Worker ohne Barcode -> generierter Ersatz-Barcode statt Crash", kw7["barcode"].startswith("MIGRATED-"))

# --- build_user_kwargs ---
user_doc = {"username": "mmuster", "role": "anwender", "is_active": True}
kw8 = build_user_kwargs(user_doc, dept_id, "hashed123")
check("User: Rolle korrekt gemappt", kw8["role"] == UserRole.MITARBEITER)
check("User: Passwort-Hash übernommen (der neu generierte, nicht der alte)", kw8["hashed_password"] == "hashed123")

# --- is_real_withdrawal ---
check("Echte Entnahme (negativ, echter Worker) -> True",
      is_real_withdrawal({"quantity": -5, "worker_barcode": "W-001"}))
check("Nachschub (positiv) -> False", not is_real_withdrawal({"quantity": 10, "worker_barcode": "W-001"}))
check("Admin-Korrektur (negativ, aber worker_barcode='admin') -> False",
      not is_real_withdrawal({"quantity": -3, "worker_barcode": "admin"}))
check("Fehlender worker_barcode -> False statt Crash", not is_real_withdrawal({"quantity": -3}))
check("Kaputte Menge -> False statt Crash", not is_real_withdrawal({"quantity": "kaputt", "worker_barcode": "W-001"}))

print("\nAlle Transform-Tests durchgelaufen.")
