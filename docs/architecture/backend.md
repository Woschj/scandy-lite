# Backend-Architektur

## Stack

FastAPI (async), SQLModel (SQLAlchemy 2.x + Pydantic) als ORM, Alembic für
Migrationen, PostgreSQL als Produktivdatenbank (SQLite nur in Tests, siehe
`docs/development/testing.md`).

## Schichtung

Kein klassisches Repository-/Service-Layer über der ORM-Session - bei der
aktuellen Größe des Projekts (ein internes Tool, keine Microservices) wäre
das zusätzliche Indirektion ohne echten Nutzen. Stattdessen:

- **`app/routers/`** - ein Router pro fachlichem Bereich, spricht direkt mit
  der SQLModel-`AsyncSession`. Jede Datei bleibt beim jeweiligen Bereich
  (Items, Consumables, Scan, Pickup, Reservations, History, Admin-Settings,
  Auth, OIDC, Badge).
- **`app/core/`** - geteilte Bausteine, die von mehreren Routern gebraucht
  werden (Auth-Dependencies, Zugriffsprüfung, Uploads, CSRF, E-Mail,
  Passwort-Reset, Migration von Scandy2, ...). Wird ein Codepfad von zwei
  Routern identisch gebraucht (z. B. `inventory_crud.py` für Items UND
  Consumables), wandert er hierher statt dupliziert zu werden - nicht vorher,
  nur bei echter Wiederverwendung.
- **`app/models/`** - ein SQLModel pro Datei, `table=True`. Tabellennamen
  Plural, Klassennamen Singular (siehe `docs/database/naming.md`).

Wird ein Router-File oder ein `core`-Modul zu groß/zu viele Zuständigkeiten
(siehe Faustregel in `CLAUDE.md`, ca. 500 Zeilen), zuerst nach fachlicher
Kohäsion aufteilen (z. B. `inventory_crud.py` als gemeinsame Basis für zwei
Router), nicht nach technischer Schicht.

## Dependency Injection

FastAPI's `Depends(...)` ist der einzige DI-Mechanismus - kein zusätzliches
Framework. Wiederkehrende Dependencies in `app/core/deps.py`:

| Dependency | Zweck |
|---|---|
| `get_current_user` | lädt den eingeloggten `User` aus dem Session-Cookie, 401/Redirect wenn keins |
| `require_staff` | zusätzlich: Mitarbeiter-Rolle in irgendeiner Abteilung oder Admin |
| `require_admin` | zusätzlich: globales Admin-Flag |
| `populate_nav_context` | füllt Template-Kontext (Nav, aktueller User, Warenkorb-Badge) - auf fast jedem Router als Router-Dependency, NICHT auf `auth`/`oidc` (siehe deren Docstrings: würde vor dem eigentlichen Login-Vorgang selbst schon umleiten) |
| `verify_csrf` | prüft `csrf_token` bei state-changing Requests, siehe `docs/security/owasp.md` |

`fastapi.Depends`/`Form`/`Query`/... im Funktions-Default ist beabsichtigtes
FastAPI-Pattern, kein B008-Verstoß (siehe `ruff.toml`
`extend-immutable-calls`).

## Datenzugriff

Async durchgehend (`AsyncSession`, `asyncpg` in Produktion). Kein
synchrones SQLAlchemy im Request-Pfad. Rechenintensive/blockierende Arbeit
(Bild-Resize via Pillow, siehe `app/core/uploads.py`) läuft explizit über
`starlette.concurrency.run_in_threadpool`, damit sie den Single-Thread-
Event-Loop nicht für alle anderen Requests blockiert.

## Hintergrund-Tasks

Kein externer Scheduler/Cron für interne Jobs. `app/core/low_stock.py`
(tägliche Mindestbestand-Mail) läuft als Endlos-Task ab `app/main.py`s
`lifespan`-Hook - für ein einzelnes internes Tool ausreichend, kein
zusätzlicher Dienst nötig. Neue wiederkehrende Jobs sollten demselben Muster
folgen, bevor über einen externen Scheduler nachgedacht wird.

## Konfiguration

`app/core/config.py` (Pydantic Settings) ist die einzige Quelle für
Umgebungsvariablen. Kein Modul liest `os.environ` direkt. `app/version.py`
ist bewusst getrennt von `config.py` - die Versionsnummer ist Teil des
Codes (Cache-Busting für `/static/...`, siehe
`app/core/templating.py::asset_version`), kein per Env-Var änderbarer
Deployment-Parameter.

## Was es NICHT gibt (Scope-Klarstellung)

Kein Plugin-System, keine Netzwerk-Discovery-Agents, keine GraphQL-API,
keine Mandantenfähigkeit über Abteilungen hinaus. Siehe
`docs/architecture/plugin-system.md` und `docs/architecture/discovery.md`
für den Hintergrund.
