"""
Erzeugt einen realistischen Demo-Datensatz: eine fiktive Firma mit 250
Mitarbeitern über 5 Abteilungen, inklusive 2 Jahren Ausleih-/Entnahme-
Historie, Reservierungen und Vormerkungen. Gedacht zum Ausprobieren/
Vorführen der App mit einer plausiblen Datenmenge - NICHT für den
Produktivbetrieb gedacht.

ACHTUNG: Setzt eine LEERE Datenbank voraus (nur Alembic-Migrationen
angewendet, sonst nichts). Bricht ab, wenn bereits Abteilungen existieren,
außer --force wird angegeben.

Nutzung:
    python -m scripts.seed_demo_data
    python -m scripts.seed_demo_data --seed 123   # abweichender Zufalls-Seed
    python -m scripts.seed_demo_data --force       # trotz vorhandener Daten fortfahren

Alle Demo-User (außer den Admins) teilen sich aus Performance-Gründen einen
vorab gehashten Platzhalter-Passworthash (bcrypt ist absichtlich langsam -
250x einzeln hashen würde spürbar dauern). Login-Passwort für alle:
"demo-passwort-2026" (siehe DEMO_PASSWORD unten). Admin-Zugangsdaten werden
am Ende ausgegeben.
"""
import argparse
import asyncio
import random
import unicodedata
import uuid
from datetime import datetime, timedelta

from sqlmodel import select

from app.core.database import async_session_maker
from app.core.security import hash_password
from app.models.common import ItemStatus, UserRole, utcnow
from app.models.consumable import Consumable, ConsumableUsage
from app.models.consumable_reservation import ConsumableReservation
from app.models.department import Department
from app.models.item import Item
from app.models.lending import Lending
from app.models.preset import Category, Location
from app.models.reservation import Reservation
from app.models.user import User
from app.models.user_department_role import UserDepartmentRole

DEMO_PASSWORD = "demo-passwort-2026"
ADMIN_PASSWORD = "admin-demo-2026"

# 1x1 transparentes PNG - Platzhalter fuer digitale Unterschriften, damit
# "Unterschrift ansehen" in der Historie ein echtes (wenn auch leeres) Bild
# zeigt statt eines kaputten <img>-Tags.
SIGNATURE_PLACEHOLDER = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

TWO_YEARS_DAYS = 730

DEPARTMENTS = [
    # code, name, ungefaehre Mitarbeiterzahl
    ("produktion", "Produktion", 70),
    ("logistik", "Logistik & Lager", 55),
    ("it", "IT & Technik", 35),
    ("verwaltung", "Verwaltung", 45),
    ("vertrieb", "Vertrieb & Kundenservice", 45),
]

# Item-/Consumable-Kataloge je Abteilung: (name, kategorie, standort)
ITEM_CATALOG = {
    "produktion": [
        ("Akkuschrauber", "Elektrowerkzeug", "Werkzeugwand A"),
        ("Bohrmaschine", "Elektrowerkzeug", "Werkzeugwand A"),
        ("Schlagbohrmaschine", "Elektrowerkzeug", "Werkzeugwand A"),
        ("Winkelschleifer", "Elektrowerkzeug", "Werkzeugwand B"),
        ("Tacker", "Handwerkzeug", "Werkzeugwand B"),
        ("Multimeter", "Messgeraet", "Messgeraete-Schrank"),
        ("Wasserwaage", "Handwerkzeug", "Werkzeugwand C"),
        ("Schraubstock", "Handwerkzeug", "Werkbank 1"),
        ("Werkzeugkoffer", "Sortiment", "Lager Produktion"),
        ("Schweissgeraet", "Elektrowerkzeug", "Schweissplatz"),
        ("Kompressor", "Maschine", "Halle 2"),
        ("Handkreissaege", "Elektrowerkzeug", "Werkzeugwand C"),
        ("Stichsaege", "Elektrowerkzeug", "Werkzeugwand C"),
        ("Schlagschrauber", "Elektrowerkzeug", "Werkzeugwand B"),
        ("Drehmomentschluessel-Set", "Handwerkzeug", "Werkbank 2"),
        ("Bandschleifer", "Elektrowerkzeug", "Werkzeugwand A"),
        ("Heissluftpistole", "Elektrowerkzeug", "Werkbank 1"),
        ("Loetkolben-Set", "Elektrowerkzeug", "Werkbank 3"),
    ],
    "logistik": [
        ("Handscanner", "Elektronik", "Wareneingang"),
        ("Palettenhubwagen", "Foerdertechnik", "Halle Lager"),
        ("Rollcontainer", "Transportmittel", "Halle Lager"),
        ("Etikettendrucker", "Elektronik", "Versand"),
        ("Wiegeplattform", "Messgeraet", "Versand"),
        ("Ladungssicherungsgurt-Set", "Zubehoer", "Verladerampe"),
        ("Funkgeraet", "Elektronik", "Lagerleitstand"),
        ("Inventurscanner", "Elektronik", "Lagerleitstand"),
        ("Sackkarre", "Transportmittel", "Halle Lager"),
        ("Stapler-Schluessel", "Schluessel", "Schluesselkasten"),
    ],
    "it": [
        ("Laptop", "IT-Geraet", "IT-Ausgabe"),
        ("Diensthandy", "IT-Geraet", "IT-Ausgabe"),
        ("Monitor", "IT-Geraet", "IT-Lager"),
        ("Dockingstation", "IT-Zubehoer", "IT-Lager"),
        ("Beamer", "Praesentationstechnik", "IT-Lager"),
        ("Konferenzkamera", "Praesentationstechnik", "IT-Lager"),
        ("Netzwerk-Tester", "Messgeraet", "Serverraum"),
        ("Ersatz-Router", "Netzwerktechnik", "Serverraum"),
        ("Tablet", "IT-Geraet", "IT-Ausgabe"),
        ("Headset", "IT-Zubehoer", "IT-Lager"),
        ("Presenter/Clicker", "Praesentationstechnik", "IT-Lager"),
    ],
    "verwaltung": [
        ("Laptop", "IT-Geraet", "Buero-Pool"),
        ("Diensthandy", "IT-Geraet", "Buero-Pool"),
        ("Aktenvernichter", "Buerogeraet", "Buero 1.OG"),
        ("Beamer", "Praesentationstechnik", "Konferenzraum"),
        ("Konferenztelefon", "Buerogeraet", "Konferenzraum"),
        ("Diktiergeraet", "Buerogeraet", "Buero-Pool"),
        ("Etikettendrucker", "Buerogeraet", "Poststelle"),
    ],
    "vertrieb": [
        ("Firmenwagen-Schluessel", "Schluessel", "Schluesselkasten"),
        ("Diensthandy", "IT-Geraet", "Vertrieb-Pool"),
        ("Laptop", "IT-Geraet", "Vertrieb-Pool"),
        ("Tablet (Kundenpraesentation)", "IT-Geraet", "Vertrieb-Pool"),
        ("Messekoffer", "Sortiment", "Lager Vertrieb"),
        ("Beamer", "Praesentationstechnik", "Vertrieb-Pool"),
    ],
}

CONSUMABLE_CATALOG = {
    "produktion": [
        ("Schrauben Sortiment", "Kleinmaterial", "Regal A1", "Packung", 40, 10),
        ("Kabelbinder", "Kleinmaterial", "Regal A1", "Packung", 30, 8),
        ("Bohrer-Set", "Verbrauchsmaterial", "Regal A2", "Set", 15, 3),
        ("Schleifpapier", "Verbrauchsmaterial", "Regal A2", "Blatt", 200, 40),
        ("Schmiermittel", "Chemikalie", "Regal B1", "Dose", 25, 5),
        ("Arbeitshandschuhe", "PSA", "Regal B2", "Paar", 60, 15),
        ("Schutzbrillen", "PSA", "Regal B2", "Stueck", 30, 10),
        ("Klebeband", "Kleinmaterial", "Regal A1", "Rolle", 40, 10),
        ("Silikon-Kartuschen", "Chemikalie", "Regal B1", "Kartusche", 20, 5),
        ("Loetzinn", "Verbrauchsmaterial", "Werkbank 3", "Rolle", 12, 3),
    ],
    "logistik": [
        ("Verpackungsband", "Verpackung", "Versand-Regal", "Rolle", 50, 10),
        ("Luftpolsterfolie", "Verpackung", "Versand-Regal", "Rolle", 20, 5),
        ("Versandkartons klein", "Verpackung", "Versand-Regal", "Stueck", 150, 30),
        ("Versandkartons gross", "Verpackung", "Versand-Regal", "Stueck", 80, 20),
        ("Etiketten-Rollen", "Verbrauchsmaterial", "Versand", "Rolle", 25, 5),
        ("Palettenfolie", "Verpackung", "Halle Lager", "Rolle", 18, 4),
        ("Handschuhe", "PSA", "Wareneingang", "Paar", 60, 15),
    ],
    "it": [
        ("USB-Sticks", "IT-Zubehoer", "IT-Lager", "Stueck", 30, 5),
        ("HDMI-Kabel", "IT-Zubehoer", "IT-Lager", "Stueck", 25, 5),
        ("Netzwerkkabel Cat6", "IT-Zubehoer", "IT-Lager", "Stueck", 40, 8),
        ("Batterien AA", "Kleinmaterial", "IT-Lager", "Packung", 30, 8),
        ("Batterien AAA", "Kleinmaterial", "IT-Lager", "Packung", 30, 8),
        ("Reinigungstuecher", "Verbrauchsmaterial", "IT-Lager", "Packung", 20, 5),
    ],
    "verwaltung": [
        ("Druckerpapier", "Buerobedarf", "Materiallager", "Packung", 60, 15),
        ("Toner Schwarz", "Buerobedarf", "Materiallager", "Stueck", 10, 3),
        ("Toner Farbe", "Buerobedarf", "Materiallager", "Stueck", 8, 2),
        ("Kugelschreiber", "Buerobedarf", "Materiallager", "Stueck", 100, 20),
        ("Post-its", "Buerobedarf", "Materiallager", "Block", 40, 10),
        ("Heftklammern", "Buerobedarf", "Materiallager", "Packung", 25, 5),
    ],
    "vertrieb": [
        ("Visitenkarten", "Marketing", "Vertrieb-Pool", "Packung", 30, 5),
        ("Werbe-Flyer", "Marketing", "Lager Vertrieb", "Stueck", 300, 50),
        ("Praesentationsmappen", "Buerobedarf", "Lager Vertrieb", "Stueck", 40, 10),
    ],
}

FIRST_NAMES = [
    "Anna", "Ben", "Clara", "David", "Emma", "Felix", "Greta", "Hannes",
    "Ida", "Jonas", "Klara", "Leon", "Mia", "Noah", "Olivia", "Paul",
    "Quirin", "Rosa", "Simon", "Tina", "Urs", "Vera", "Wolfgang", "Xenia",
    "Yasmin", "Zoe", "Anton", "Bianca", "Christian", "Diana", "Erik",
    "Franziska", "Gerd", "Helena", "Ivo", "Julia", "Karl", "Laura", "Max",
    "Nina", "Oliver", "Petra", "Robert", "Sabine", "Thomas", "Ulla",
    "Viktor", "Wanda", "Yannick", "Zora",
]
LAST_NAMES = [
    "Müller", "Schmidt", "Schneider", "Fischer", "Weber", "Meyer", "Wagner",
    "Becker", "Schulz", "Hoffmann", "Schäfer", "Koch", "Bauer", "Richter",
    "Klein", "Wolf", "Neumann", "Schwarz", "Zimmermann", "Braun", "Krüger",
    "Hofmann", "Hartmann", "Lange", "Werner", "Schmitt", "Krause", "Meier",
    "Lehmann", "Schmid", "Schulze", "Maier", "Köhler", "Herrmann", "König",
    "Walter", "Mayer", "Huber", "Kaiser", "Fuchs", "Peters", "Lang", "Scholz",
    "Möller", "Weiß", "Jung", "Hahn", "Schubert", "Vogel", "Friedrich",
]

_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def slugify_name(name: str) -> str:
    lowered = name.lower().translate(_UMLAUT_MAP)
    normalized = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode("ascii")
    return normalized


def business_datetime(rng: random.Random, start: datetime, end: datetime) -> datetime:
    """Zufälliger Zeitpunkt im Bereich, mit Gewicht auf Werktage + Arbeitszeit
    (7-18 Uhr) - reine Gleichverteilung würde unrealistisch viele
    Wochenend-/Nacht-Ausleihen erzeugen."""
    span_days = max((end - start).days, 1)
    for _ in range(8):
        day_offset = rng.randint(0, span_days)
        candidate_day = start + timedelta(days=day_offset)
        if candidate_day.weekday() < 5 or rng.random() < 0.05:
            hour = rng.choices(range(6, 20), weights=[1, 2, 4, 6, 8, 8, 6, 5, 5, 6, 8, 7, 5, 3])[0]
            minute = rng.randint(0, 59)
            return candidate_day.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return start


async def main(seed: int, force: bool) -> None:
    rng = random.Random(seed)

    async with async_session_maker() as session:
        existing = (await session.exec(select(Department.id).limit(1))).first()
        if existing and not force:
            print("FEHLER: Es existieren bereits Abteilungen - Datenbank ist nicht leer.")
            print("Mit --force trotzdem fortfahren (fügt zusätzliche Daten hinzu).")
            return

        now = utcnow()
        start = now - timedelta(days=TWO_YEARS_DAYS)

        # --- Abteilungen ----------------------------------------------------
        departments: dict[str, Department] = {}
        for code, name, _headcount in DEPARTMENTS:
            dept = Department(code=code, name=name, created_at=start)
            session.add(dept)
            departments[code] = dept
        await session.commit()
        print(f"{len(departments)} Abteilungen angelegt.")

        # --- Kategorie-/Standort-Presets ------------------------------------
        presets: list[Category | Location] = []
        for code, dept in departments.items():
            seen_cat: set[str] = set()
            seen_loc: set[str] = set()
            for name, category, location in ITEM_CATALOG.get(code, []) + [
                (c[0], c[1], c[2]) for c in CONSUMABLE_CATALOG.get(code, [])
            ]:
                if category not in seen_cat:
                    presets.append(Category(name=category, department_id=dept.id))
                    seen_cat.add(category)
                if location not in seen_loc:
                    presets.append(Location(name=location, department_id=dept.id))
                    seen_loc.add(location)
        session.add_all(presets)
        await session.commit()
        print(f"{len(presets)} Kategorie-/Standort-Presets angelegt.")

        # --- Benutzer (Mitarbeiter) ------------------------------------------
        demo_hash = hash_password(DEMO_PASSWORD)
        admin_hash = hash_password(ADMIN_PASSWORD)

        used_usernames: set[str] = set()
        used_barcodes: set[str] = set()

        def unique_username(first: str, last: str) -> str:
            base = f"{slugify_name(first)}.{slugify_name(last)}"
            candidate = base
            suffix = 1
            while candidate in used_usernames:
                suffix += 1
                candidate = f"{base}{suffix}"
            used_usernames.add(candidate)
            return candidate

        def next_barcode(prefix: str) -> str:
            counter = 1
            while True:
                candidate = f"{prefix}-{counter:05d}"
                if candidate not in used_barcodes:
                    used_barcodes.add(candidate)
                    return candidate
                counter += 1

        users: list[User] = []
        user_department_roles: list[UserDepartmentRole] = []

        # 3 globale Admins (department-uebergreifend, keine expliziten Rollen noetig)
        for i in range(3):
            first = rng.choice(FIRST_NAMES)
            last = rng.choice(LAST_NAMES)
            username = unique_username(first, last) if i > 0 else "admin"
            admin = User(
                username=username,
                is_admin=True,
                hashed_password=admin_hash,
                first_name=first,
                last_name=last,
                barcode=next_barcode("MA"),
                department_id=rng.choice(list(departments.values())).id,
                approved_at=start,
                created_at=start,
            )
            users.append(admin)

        # Regulaere Mitarbeiter, verteilt auf die 5 Abteilungen
        dept_codes = [c for c, _n, _h in DEPARTMENTS]
        headcounts = {c: h for c, _n, h in DEPARTMENTS}
        for code in dept_codes:
            dept = departments[code]
            for _ in range(headcounts[code]):
                first = rng.choice(FIRST_NAMES)
                last = rng.choice(LAST_NAMES)
                username = unique_username(first, last)
                joined_at = start + timedelta(days=rng.randint(0, TWO_YEARS_DAYS - 1))
                user = User(
                    username=username,
                    is_admin=False,
                    hashed_password=demo_hash,
                    first_name=first,
                    last_name=last,
                    barcode=next_barcode("MA"),
                    department_id=dept.id,
                    approved_at=joined_at,
                    created_at=joined_at,
                )
                users.append(user)

                role = UserRole.MITARBEITER if rng.random() < 0.15 else UserRole.NUTZER
                user_department_roles.append(
                    UserDepartmentRole(user_id=user.id, department_id=dept.id, role=role, created_at=joined_at)
                )
                # ~10% zusaetzlich Nutzer-Rolle in einer zweiten, zufaelligen Abteilung
                if rng.random() < 0.10:
                    other_code = rng.choice([c for c in dept_codes if c != code])
                    other_dept = departments[other_code]
                    user_department_roles.append(
                        UserDepartmentRole(
                            user_id=user.id, department_id=other_dept.id,
                            role=UserRole.NUTZER, created_at=joined_at,
                        )
                    )

        session.add_all(users)
        await session.commit()
        session.add_all(user_department_roles)
        await session.commit()
        print(f"{len(users)} Benutzer angelegt ({len(user_department_roles)} Abteilungsrollen).")

        # Nur User mit einer Rolle koennen sinnvoll als "Ausleiher" auftreten -
        # Admins duerfen auch, sind aber selten die tatsaechlichen Ausleiher.
        borrowers_by_dept: dict[str, list[User]] = {code: [] for code in dept_codes}
        role_dept_ids = {(r.user_id, r.department_id) for r in user_department_roles}
        user_by_id = {u.id: u for u in users}
        for user_id, dept_id in role_dept_ids:
            for code, dept in departments.items():
                if dept.id == dept_id:
                    borrowers_by_dept[code].append(user_by_id[user_id])

        # --- Gegenstaende -----------------------------------------------------
        items: list[Item] = []
        items_by_dept: dict[str, list[Item]] = {code: [] for code in dept_codes}
        for code, dept in departments.items():
            catalog = ITEM_CATALOG.get(code, [])
            target_count = 30
            i = 0
            while i < target_count:
                name, category, location = catalog[i % len(catalog)]
                suffix = f" #{i // len(catalog) + 1}" if i >= len(catalog) else ""
                item = Item(
                    barcode=next_barcode("ITM"),
                    name=f"{name}{suffix}",
                    category=category,
                    location=location,
                    department_id=dept.id,
                    status=ItemStatus.VERFUEGBAR,
                    created_at=start + timedelta(days=rng.randint(0, 60)),
                )
                items.append(item)
                items_by_dept[code].append(item)
                i += 1
        session.add_all(items)
        await session.commit()
        print(f"{len(items)} Gegenstände angelegt.")

        # --- Verbrauchsmaterial ------------------------------------------------
        consumables: list[Consumable] = []
        consumables_by_dept: dict[str, list[Consumable]] = {code: [] for code in dept_codes}
        for code, dept in departments.items():
            catalog = CONSUMABLE_CATALOG.get(code, [])
            target_count = 15
            i = 0
            while i < target_count:
                name, category, location, unit, quantity, min_quantity = catalog[i % len(catalog)]
                suffix = f" #{i // len(catalog) + 1}" if i >= len(catalog) else ""
                jitter = rng.uniform(0.6, 1.3)
                consumable = Consumable(
                    barcode=next_barcode("CON"),
                    name=f"{name}{suffix}",
                    category=category,
                    location=location,
                    unit=unit,
                    quantity=max(0, round(quantity * jitter)),
                    min_quantity=min_quantity,
                    department_id=dept.id,
                    created_at=start + timedelta(days=rng.randint(0, 60)),
                )
                consumables.append(consumable)
                consumables_by_dept[code].append(consumable)
                i += 1
        session.add_all(consumables)
        await session.commit()
        print(f"{len(consumables)} Verbrauchsmaterial-Einträge angelegt.")

        # --- Ausleih-Historie (Lendings) ---------------------------------------
        lendings: list[Lending] = []
        open_item_ids: set[uuid.UUID] = set()
        for code, dept_items in items_by_dept.items():
            borrowers = borrowers_by_dept.get(code) or list(users)
            for item in dept_items:
                # ~4% der Gegenstaende dauerhaft ausser Betrieb (kein Verleih mehr)
                if rng.random() < 0.04:
                    item.status = rng.choice([ItemStatus.DEFEKT, ItemStatus.AUSGEMUSTERT])
                    continue

                lend_count = rng.randint(10, 60)
                cursor = start
                last_lending: Lending | None = None
                for _ in range(lend_count):
                    if cursor >= now - timedelta(days=1):
                        break
                    lent_at = business_datetime(rng, cursor, min(cursor + timedelta(days=30), now))
                    if lent_at <= cursor:
                        lent_at = cursor + timedelta(hours=1)
                    worker = rng.choice(borrowers)
                    duration_hours = rng.choices(
                        [4, 24, 72, 168, 336],
                        weights=[35, 30, 20, 10, 5],
                    )[0]
                    returned_at = lent_at + timedelta(hours=duration_hours)
                    is_last_possible = returned_at >= now
                    signature = SIGNATURE_PLACEHOLDER if rng.random() < 0.3 else None
                    lending = Lending(
                        item_id=item.id,
                        item_name_snapshot=item.name,
                        item_barcode_snapshot=item.barcode,
                        worker_id=worker.id,
                        worker_name_snapshot=worker.full_name,
                        department_id=item.department_id,
                        department_name_snapshot=departments[code].name,
                        lent_at=lent_at,
                        returned_at=None if is_last_possible else returned_at,
                        signature=signature,
                        created_at=lent_at,
                        updated_at=lent_at if is_last_possible else returned_at,
                    )
                    lendings.append(lending)
                    last_lending = lending
                    if is_last_possible:
                        break
                    cursor = returned_at

                # ~8% Chance, dass der letzte Vorgang noch offen ist (aktuell ausgeliehen)
                if last_lending is not None and last_lending.returned_at is None:
                    item.status = ItemStatus.AUSGELIEHEN
                    open_item_ids.add(item.id)
                elif last_lending is not None and rng.random() < 0.08 and item.id not in open_item_ids:
                    # Letzte (bereits zurückgegebene) Ausleihe nachträglich wieder oeffnen
                    last_lending.returned_at = None
                    last_lending.updated_at = last_lending.lent_at
                    item.status = ItemStatus.AUSGELIEHEN
                    open_item_ids.add(item.id)

        session.add_all(items)  # Status-Änderungen
        session.add_all(lendings)
        await session.commit()
        print(f"{len(lendings)} Ausleih-Vorgänge angelegt ({len(open_item_ids)} aktuell offen).")

        # --- Verbrauchsmaterial-Entnahmen ---------------------------------------
        usages: list[ConsumableUsage] = []
        for code, dept_consumables in consumables_by_dept.items():
            borrowers = borrowers_by_dept.get(code) or list(users)
            for consumable in dept_consumables:
                usage_count = rng.randint(15, 45)
                for _ in range(usage_count):
                    used_at = business_datetime(rng, start, now)
                    worker = rng.choice(borrowers)
                    usages.append(
                        ConsumableUsage(
                            consumable_id=consumable.id,
                            consumable_name_snapshot=consumable.name,
                            worker_id=worker.id,
                            worker_name_snapshot=worker.full_name,
                            department_id=consumable.department_id,
                            department_name_snapshot=departments[code].name,
                            quantity=rng.randint(1, 5),
                            used_at=used_at,
                            created_at=used_at,
                            updated_at=used_at,
                        )
                    )
        session.add_all(usages)
        await session.commit()
        print(f"{len(usages)} Verbrauchsmaterial-Entnahmen angelegt.")

        # --- Reservierungen (Gegenstände) ----------------------------------------
        reservations: list[Reservation] = []
        for code, dept_items in items_by_dept.items():
            borrowers = borrowers_by_dept.get(code) or []
            if not borrowers or not dept_items:
                continue
            for _ in range(rng.randint(80, 160)):
                item = rng.choice(dept_items)
                worker = rng.choice(borrowers)
                reserved_at = business_datetime(rng, start, now)
                outcome = rng.random()
                fulfilled_at = reserved_at + timedelta(hours=rng.randint(1, 48)) if outcome < 0.55 else None
                cancelled_at = reserved_at + timedelta(hours=rng.randint(1, 24)) if 0.55 <= outcome < 0.85 else None
                reservations.append(
                    Reservation(
                        item_id=item.id,
                        item_name_snapshot=item.name,
                        item_barcode_snapshot=item.barcode,
                        worker_id=worker.id,
                        worker_name_snapshot=worker.full_name,
                        department_id=item.department_id,
                        department_name_snapshot=departments[code].name,
                        fulfilled_at=fulfilled_at,
                        cancelled_at=cancelled_at,
                        created_at=reserved_at,
                        updated_at=fulfilled_at or cancelled_at or reserved_at,
                    )
                )
        session.add_all(reservations)
        await session.commit()
        print(f"{len(reservations)} Reservierungen angelegt.")

        # --- Vormerkungen (Verbrauchsmaterial) -----------------------------------
        consumable_reservations: list[ConsumableReservation] = []
        for code, dept_consumables in consumables_by_dept.items():
            borrowers = borrowers_by_dept.get(code) or []
            if not borrowers or not dept_consumables:
                continue
            for _ in range(rng.randint(50, 100)):
                consumable = rng.choice(dept_consumables)
                worker = rng.choice(borrowers)
                reserved_at = business_datetime(rng, start, now)
                outcome = rng.random()
                fulfilled_at = reserved_at + timedelta(hours=rng.randint(1, 48)) if outcome < 0.6 else None
                cancelled_at = reserved_at + timedelta(hours=rng.randint(1, 24)) if 0.6 <= outcome < 0.85 else None
                consumable_reservations.append(
                    ConsumableReservation(
                        consumable_id=consumable.id,
                        consumable_name_snapshot=consumable.name,
                        worker_id=worker.id,
                        worker_name_snapshot=worker.full_name,
                        department_id=consumable.department_id,
                        department_name_snapshot=departments[code].name,
                        quantity=rng.randint(1, 10),
                        fulfilled_at=fulfilled_at,
                        cancelled_at=cancelled_at,
                        created_at=reserved_at,
                        updated_at=fulfilled_at or cancelled_at or reserved_at,
                    )
                )
        session.add_all(consumable_reservations)
        await session.commit()
        print(f"{len(consumable_reservations)} Verbrauchsmaterial-Vormerkungen angelegt.")

        print("")
        print("=== Fertig ===")
        print(f"Admin-Login (Beispiel):    admin / {ADMIN_PASSWORD}")
        print(f"Alle übrigen Demo-User:    <vorname>.<nachname> / {DEMO_PASSWORD}")
        print("(Benutzernamen z.B. über Einstellungen -> Benutzer einsehen)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Realistischen Demo-Datensatz erzeugen")
    parser.add_argument("--seed", type=int, default=42, help="Zufalls-Seed für Reproduzierbarkeit")
    parser.add_argument("--force", action="store_true", help="Auch bei bereits vorhandenen Abteilungen fortfahren")
    args = parser.parse_args()

    asyncio.run(main(args.seed, args.force))
