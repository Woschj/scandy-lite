"""
Kern-Migrationslogik: nimmt bereits aus MongoDB gelesene, einfache Python-
Datenstrukturen entgegen (Listen von dicts) und schreibt sie nach Postgres.

Bewusst getrennt von migrate_from_mongodb.py (dem eigentlichen CLI-Skript,
das die MongoDB-Verbindung aufbaut) - dadurch lässt sich diese Funktion mit
synthetischen Testdaten vollständig durchspielen, ohne eine echte MongoDB-
Instanz zu brauchen. Siehe test_migrate.py.

migrate() orchestriert acht Teilschritte (Abteilungen -> Presets -> Benutzer
-> Mitarbeiter-Ausweise -> Gegenstände -> Verbrauchsmaterial -> Ausleihen ->
Entnahmen) in dieser Reihenfolge, weil jeder spätere Schritt die ID-Zuordnung
(z.B. barcode -> neue/bestehende Item-ID) der vorherigen braucht, um Fremd-
schlüssel korrekt aufzulösen. Jeder Schritt ist als eigene _migrate_*-Funktion
ausgelagert, damit die Reihenfolge/Abhängigkeiten hier oben auf einen Blick
sichtbar sind, statt in einer einzigen sehr langen Funktion zu verschwinden.
"""
from collections import defaultdict

from sqlmodel import Session, select

from app.core.security import hash_password
from app.models.common import ItemStatus
from app.models.consumable import Consumable, ConsumableUsage
from app.models.department import Department
from app.models.item import Item
from app.models.lending import Lending
from app.models.preset import Category, Location
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole
from migrations_legacy.transform import (
    build_consumable_kwargs,
    build_item_kwargs,
    build_user_kwargs,
    build_worker_kwargs,
    clean_str,
    generate_temp_password,
    is_real_withdrawal,
    map_user_role,
    slugify_department_code,
    to_datetime,
)


def _resolve_department(dept_id_by_name: dict, name: str | None):
    name = clean_str(name)
    if not name or name not in dept_id_by_name:
        return None
    return dept_id_by_name[name]


def _migrate_departments(session: Session, data: dict, apply: bool, report: dict) -> dict[str, object]:
    dept_id_by_name: dict[str, object] = {}
    for name in sorted(set(n for n in data.get("department_names", []) if clean_str(n))):
        code = slugify_department_code(name)
        existing = session.exec(select(Department).where(Department.code == code)).first()
        if existing:
            dept_id_by_name[name] = existing.id
            continue
        dept = Department(code=code, name=name)
        if apply:
            session.add(dept)
            session.flush()
            dept_id_by_name[name] = dept.id
        else:
            dept_id_by_name[name] = f"<würde-anlegen:{code}>"
        report["departments_created"] += 1
    return dept_id_by_name


def _migrate_presets(session: Session, data: dict, apply: bool, report: dict, dept_id_by_name: dict) -> None:
    for dept_name, categories in (data.get("categories_by_department") or {}).items():
        dept_id = _resolve_department(dept_id_by_name, dept_name)
        if dept_id is None or not apply:
            report["categories_created"] += len(categories) if not apply else 0
            continue
        for cat_name in categories:
            cat_name = clean_str(cat_name)
            if not cat_name:
                continue
            exists = session.exec(
                select(Category).where(Category.department_id == dept_id, Category.name == cat_name)
            ).first()
            if not exists:
                session.add(Category(name=cat_name, department_id=dept_id))
                report["categories_created"] += 1

    for dept_name, locations in (data.get("locations_by_department") or {}).items():
        dept_id = _resolve_department(dept_id_by_name, dept_name)
        if dept_id is None or not apply:
            report["locations_created"] += len(locations) if not apply else 0
            continue
        for loc_name in locations:
            loc_name = clean_str(loc_name)
            if not loc_name:
                continue
            exists = session.exec(
                select(Location).where(Location.department_id == dept_id, Location.name == loc_name)
            ).first()
            if not exists:
                session.add(Location(name=loc_name, department_id=dept_id))
                report["locations_created"] += 1

    if apply:
        session.flush()


def _migrate_users(
    session: Session, data: dict, apply: bool, report: dict, warnings: list, generated_passwords: list,
    dept_id_by_name: dict,
) -> dict[str, object]:
    """Benutzer (+ generiertes Passwort, altes Hash-Verfahren inkompatibel)."""
    user_id_by_username: dict[str, object] = {}
    for user_doc in data.get("users", []):
        username = clean_str(user_doc.get("username"))
        if not username:
            warnings.append("User ohne Benutzernamen übersprungen")
            continue
        existing = session.exec(select(User).where(User.username == username)).first()
        if existing:
            user_id_by_username[username] = existing.id
            report["users_skipped_existing"] += 1
            continue

        dept_name = user_doc.get("default_department") or (user_doc.get("allowed_departments") or [None])[0]
        dept_id = _resolve_department(dept_id_by_name, dept_name)
        role = map_user_role(user_doc.get("role"))

        temp_password = generate_temp_password()
        kwargs = build_user_kwargs(user_doc, hash_password(temp_password) if apply else "")
        if apply:
            user = User(**kwargs)
            session.add(user)
            session.flush()
            user_id_by_username[username] = user.id
            generated_passwords.append((username, temp_password))

            # Abteilungs-Rolle anlegen (Admin ist ein globales Flag, braucht
            # keinen UserDepartmentRole-Eintrag - siehe app/core/access.py).
            if not user.is_admin:
                if dept_id is not None:
                    session.add(UserDepartmentRole(user_id=user.id, department_id=dept_id, role=role))
                    report["user_department_roles_created"] += 1
                else:
                    warnings.append(
                        f"User '{username}': keine Abteilung zuordenbar - Zugriffsrolle muss manuell "
                        "unter Einstellungen -> Zugriff nachgetragen werden."
                    )
        else:
            user_id_by_username[username] = f"<würde-anlegen:{username}>"
        report["users_created"] += 1
    return user_id_by_username


def _migrate_workers(
    session: Session, data: dict, apply: bool, report: dict, dept_id_by_name: dict, user_id_by_username: dict,
) -> dict[str, object]:
    """Mitarbeiter-Ausweise (jetzt Teil von User, siehe app/models/user.py).

    Gehört der Mitarbeiter-Datensatz zu einem bereits migrierten/vorhandenen
    Login (per username verknüpft) -> Ausweis-Felder auf DIESEN User
    schreiben, statt eine zweite, separate Zeile anzulegen (User und
    Mitarbeiter-Ausweis sind seit der Vereinheitlichung dieselbe Entität).
    Kein passender Login -> neuer User OHNE Passwort (reiner Ausweis, kann
    sich nicht einloggen - genau wie vorher ein Worker ohne user_id)."""
    worker_id_by_barcode: dict[str, object] = {}
    for worker_doc in data.get("workers", []):
        barcode = clean_str(worker_doc.get("barcode"))
        dept_id = _resolve_department(dept_id_by_name, worker_doc.get("department"))
        if dept_id is None:
            report["workers_skipped_no_department"] += 1
            continue

        if barcode:
            existing = session.exec(
                select(User).where(User.barcode == barcode, User.deleted_at.is_(None))
            ).first()
            if existing:
                worker_id_by_barcode[barcode] = existing.id
                report["workers_skipped_existing"] += 1
                continue

        kwargs = build_worker_kwargs(worker_doc, dept_id)
        linked_username = clean_str(worker_doc.get("username"))
        if apply:
            linked_user = user_id_by_username.get(linked_username) if linked_username else None
            if linked_user is not None and not str(linked_user).startswith("<"):
                target_user = session.get(User, linked_user)
                target_user.first_name = kwargs["first_name"]
                target_user.last_name = kwargs["last_name"]
                target_user.barcode = kwargs["barcode"]
                target_user.department_id = kwargs["department_id"]
                session.add(target_user)
                session.flush()
                worker_id_by_barcode[kwargs["barcode"]] = target_user.id
            else:
                worker_user = User(
                    username=f"mitarbeiter-{kwargs['barcode']}".lower(),
                    is_admin=False,
                    hashed_password=None,
                    **kwargs,
                )
                session.add(worker_user)
                session.flush()
                worker_id_by_barcode[kwargs["barcode"]] = worker_user.id
        else:
            worker_id_by_barcode[kwargs["barcode"]] = f"<würde-anlegen:{kwargs['barcode']}>"
        report["workers_created"] += 1
    return worker_id_by_barcode


def _migrate_items(session: Session, data: dict, apply: bool, report: dict, dept_id_by_name: dict) -> dict[str, object]:
    """Gegenstände (aus 'tools')."""
    item_id_by_barcode: dict[str, object] = {}
    for tool_doc in data.get("tools", []):
        barcode = clean_str(tool_doc.get("barcode"))
        dept_id = _resolve_department(dept_id_by_name, tool_doc.get("department"))
        if dept_id is None:
            report["items_skipped_no_department"] += 1
            continue
        if not barcode:
            report["items_skipped_no_barcode"] += 1
            continue

        existing = session.exec(select(Item).where(Item.barcode == barcode, Item.deleted_at.is_(None))).first()
        if existing:
            item_id_by_barcode[barcode] = existing.id
            report["items_skipped_existing"] += 1
            continue

        kwargs = build_item_kwargs(tool_doc, dept_id)
        if apply:
            item = Item(**kwargs)
            session.add(item)
            session.flush()
            item_id_by_barcode[barcode] = item.id
        else:
            item_id_by_barcode[barcode] = f"<würde-anlegen:{barcode}>"
        report["items_created"] += 1
    return item_id_by_barcode


def _migrate_consumables(session: Session, data: dict, apply: bool, report: dict, dept_id_by_name: dict) -> dict[str, object]:
    consumable_id_by_barcode: dict[str, object] = {}
    for cons_doc in data.get("consumables", []):
        barcode = clean_str(cons_doc.get("barcode"))
        dept_id = _resolve_department(dept_id_by_name, cons_doc.get("department"))
        if dept_id is None:
            report["consumables_skipped_no_department"] += 1
            continue
        if not barcode:
            report["consumables_skipped_no_barcode"] += 1
            continue

        existing = session.exec(
            select(Consumable).where(Consumable.barcode == barcode, Consumable.deleted_at.is_(None))
        ).first()
        if existing:
            consumable_id_by_barcode[barcode] = existing.id
            report["consumables_skipped_existing"] += 1
            continue

        kwargs = build_consumable_kwargs(cons_doc, dept_id)
        if apply:
            consumable = Consumable(**kwargs)
            session.add(consumable)
            session.flush()
            consumable_id_by_barcode[barcode] = consumable.id
        else:
            consumable_id_by_barcode[barcode] = f"<würde-anlegen:{barcode}>"
        report["consumables_created"] += 1
    return consumable_id_by_barcode


def _migrate_lendings(
    session: Session, data: dict, apply: bool, report: dict,
    dept_id_by_name: dict, item_id_by_barcode: dict, worker_id_by_barcode: dict,
) -> None:
    """Ausleihen (offene UND abgeschlossene)."""
    for lending_doc in data.get("lendings", []):
        tool_barcode = clean_str(lending_doc.get("tool_barcode"))
        worker_barcode = clean_str(lending_doc.get("worker_barcode"))
        item_id = item_id_by_barcode.get(tool_barcode)
        worker_id = worker_id_by_barcode.get(worker_barcode)

        if item_id is None or worker_id is None:
            report["lendings_skipped_broken_reference"] += 1
            continue

        lent_at = to_datetime(lending_doc.get("lent_at")) or to_datetime(lending_doc.get("created_at"))
        returned_at = to_datetime(lending_doc.get("returned_at"))
        if lent_at is None:
            report["lendings_skipped_no_date"] += 1
            continue

        lending_department_id = _resolve_department(dept_id_by_name, lending_doc.get("department"))
        if lending_department_id is None:
            # department_id ist NOT NULL - falls am Lending-Dokument selbst keine
            # Abteilung hinterlegt war, die des migrierten Gegenstands übernehmen
            fallback_item = session.get(Item, item_id) if apply and not str(item_id).startswith("<") else None
            lending_department_id = fallback_item.department_id if fallback_item else None
        if lending_department_id is None:
            report["lendings_skipped_broken_reference"] += 1
            continue

        if apply:
            # Duplikat-Schutz: dieselbe Kombination (Gegenstand, Mitarbeiter,
            # Ausleihzeitpunkt) gab's schon -> zweiter Lauf des Skripts legt
            # nichts doppelt an.
            already_exists = session.exec(
                select(Lending).where(
                    Lending.item_id == item_id, Lending.worker_id == worker_id, Lending.lent_at == lent_at
                )
            ).first()
            if already_exists:
                report["lendings_skipped_existing"] += 1
                continue

            lending = Lending(
                item_id=item_id, worker_id=worker_id, department_id=lending_department_id,
                lent_at=lent_at, returned_at=returned_at,
            )
            session.add(lending)

            # Falls diese Ausleihe offen ist (kein returned_at), den migrierten
            # Gegenstand konsistent auf "ausgeliehen" setzen - das ist die
            # Quelle der Wahrheit für den Status, nicht das Status-Feld im
            # alten Tool-Dokument (siehe transform.map_item_status-Kommentar).
            if returned_at is None:
                item = session.get(Item, item_id)
                if item and item.status == ItemStatus.VERFUEGBAR:
                    item.status = ItemStatus.AUSGELIEHEN
                    session.add(item)
        report["lendings_created"] += 1


def _migrate_consumable_usages(
    session: Session, data: dict, apply: bool, report: dict,
    consumable_id_by_barcode: dict, worker_id_by_barcode: dict,
) -> None:
    """Verbrauchsmaterial-Entnahmen (nur echte Entnahmen, s. transform.is_real_withdrawal)."""
    for usage_doc in data.get("consumable_usages", []):
        if not is_real_withdrawal(usage_doc):
            report["consumable_usages_skipped_not_withdrawal"] += 1
            continue

        consumable_barcode = clean_str(usage_doc.get("consumable_barcode"))
        worker_barcode = clean_str(usage_doc.get("worker_barcode"))
        consumable_id = consumable_id_by_barcode.get(consumable_barcode)
        worker_id = worker_id_by_barcode.get(worker_barcode)

        if consumable_id is None or worker_id is None:
            report["consumable_usages_skipped_broken_reference"] += 1
            continue

        used_at = to_datetime(usage_doc.get("used_at")) or to_datetime(usage_doc.get("created_at"))
        if used_at is None:
            report["consumable_usages_skipped_no_date"] += 1
            continue

        try:
            quantity = abs(int(float(usage_doc.get("quantity", 0))))
        except (TypeError, ValueError):
            report["consumable_usages_skipped_bad_quantity"] += 1
            continue

        if apply:
            already_exists = session.exec(
                select(ConsumableUsage).where(
                    ConsumableUsage.consumable_id == consumable_id,
                    ConsumableUsage.worker_id == worker_id,
                    ConsumableUsage.used_at == used_at,
                    ConsumableUsage.quantity == quantity,
                )
            ).first()
            if already_exists:
                report["consumable_usages_skipped_existing"] += 1
                continue

            usage = ConsumableUsage(
                consumable_id=consumable_id, worker_id=worker_id,
                quantity=quantity, used_at=used_at,
            )
            session.add(usage)
        report["consumable_usages_created"] += 1


def migrate(session: Session, data: dict, *, apply: bool) -> dict:
    """
    data erwartet folgende Keys (jeweils Liste von dicts, wie sie roh aus den
    Mongo-Collections kommen):
      department_names: list[str]                 (schon deduplizierte Namen)
      categories_by_department: dict[str, list[str]]
      locations_by_department: dict[str, list[str]]
      users: list[dict]                            (Mongo 'users'-Collection)
      workers: list[dict]                          (Mongo 'workers'-Collection)
      tools: list[dict]                            (Mongo 'tools'-Collection)
      consumables: list[dict]                      (Mongo 'consumables'-Collection)
      lendings: list[dict]                         (Mongo 'lendings'-Collection)
      consumable_usages: list[dict]                (Mongo 'consumable_usages'-Collection)

    apply=False: es wird NICHTS geschrieben, nur gezählt/geprüft (Trockenlauf).
    Gibt einen Report zurück: Zähler + Liste generierter Passwörter + Warnungen.
    """
    report = defaultdict(int)
    warnings: list[str] = []
    generated_passwords: list[tuple[str, str]] = []  # (username, klartext-passwort)

    dept_id_by_name = _migrate_departments(session, data, apply, report)
    _migrate_presets(session, data, apply, report, dept_id_by_name)
    user_id_by_username = _migrate_users(session, data, apply, report, warnings, generated_passwords, dept_id_by_name)
    worker_id_by_barcode = _migrate_workers(session, data, apply, report, dept_id_by_name, user_id_by_username)
    item_id_by_barcode = _migrate_items(session, data, apply, report, dept_id_by_name)
    consumable_id_by_barcode = _migrate_consumables(session, data, apply, report, dept_id_by_name)
    _migrate_lendings(session, data, apply, report, dept_id_by_name, item_id_by_barcode, worker_id_by_barcode)
    _migrate_consumable_usages(session, data, apply, report, consumable_id_by_barcode, worker_id_by_barcode)

    if apply:
        session.commit()

    return {
        "report": dict(report),
        "warnings": warnings,
        "generated_passwords": generated_passwords,
    }
