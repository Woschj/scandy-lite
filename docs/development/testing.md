# Tests

## Werkzeuge

`pytest` + `pytest-asyncio`, `httpx.AsyncClient` (ASGI-Transport) gegen die
echte FastAPI-App - keine gemockte Anwendungsschicht. 21 Testdateien unter
`tests/`.

## Grundmuster: echte HTTP-Roundtrips, kein reines Unit-Testing der Funktion

Ein Test ruft die tatsächliche Route auf (Login, Formular-Submit, ...) und
prüft Statuscode/Redirect/Datenbankzustand danach - nicht nur, dass eine
einzelne Funktion isoliert das richtige zurückgibt. Grund: viele Bugs in
diesem Projekt saßen in der Verdrahtung (CSRF, Redirect-Ziel,
Berechtigungsprüfung), nicht in der reinen Geschäftslogik - reine
Unit-Tests hätten sie nicht gefangen.

## Datenbank in Tests

SQLite, **datei-basiert** (nicht `:memory:`) - eine eigene, echte
Connection mit korrekter Transaktions-Isolation, nötig für Tests, die
echte Nebenläufigkeit prüfen (`test_consumable_stock_race.py`).
**`PRAGMA foreign_keys=ON` ist Pflicht** in jeder Test-Engine-Fixture -
SQLite prüft Fremdschlüssel sonst standardmäßig NICHT, was in der
Vergangenheit reale, gegen Postgres krachende Bugs verdeckt hat (Enum-Typ
doppelt angelegt, FK-Verletzung beim User-Löschen - siehe
`PROJECT_STATUS_FOR_CLAUDE_CODE.md` Abschnitt 7). Neue Test-Fixtures immer
von `tests/conftest.py` ableiten statt eine eigene Engine ohne dieses
Pragma aufzusetzen.

`app.core.database.get_session` wird per FastAPI `dependency_overrides` auf
die Test-Engine umgebogen - Tests laufen gegen dieselbe Route-Logik wie
Produktion, nur mit anderer DB-Verbindung.

## Was vor jeder Änderung getestet werden sollte

Aus `CLAUDE.md`: welche Tests fehlen, welche Edge Cases gibt es, kann
etwas regressieren. Konkret für dieses Projekt besonders relevant:

- **Berechtigung:** wirkt eine neue Route/ein neues Feld korrekt pro
  Abteilung (Mitarbeiter vs. Nutzer vs. Admin)?
- **CSRF:** hat jedes neue state-changing Formular den Token?
- **Soft-Delete/Papierkorb:** bleibt abgeschlossene Historie beim Löschen
  einer referenzierten Entität erhalten (Snapshot statt kaputter FK)?
- **Nebenläufigkeit:** bei Bestandsänderungen (Verbrauchsmaterial) - kann
  ein Race Condition zum Überverkaufen führen?

## JS-Änderungen

Kein Test-Runner für JS im Projekt. Bei nicht-trivialen Änderungen an
`app/static/js/*.js`: mindestens `node --check <datei>` für Syntax, bei
DOM-Verhalten ggf. `jsdom` ad hoc nutzen, um den ALTEN (fehlerhaften)
Zustand nachzubauen und zu bestätigen, dass ein Fix wirklich greift (so
wurde z. B. der Event-Phasen-Bug in `form-guard.js`/`signature.js`
verifiziert).

## CI

`.github/workflows/ci.yml`: komplette Testsuite bei jedem Push/PR auf
`master`, plus ein reiner Docker-Build-Check (stellt sicher, dass das
Image baubar bleibt, pusht aber nichts). Linting (`ruff check .`) läuft
**nicht** in der CI, nur lokal (siehe `docs/development/python.md`).
