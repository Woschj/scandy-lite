# Python

## Version &amp; Stil

Python 3.12+ (siehe `ruff.toml` `target-version`). Type Hints
durchgängig, `pathlib` statt String-Pfadverkettung, `logging` statt
`print()` (Logger-Name `"scandy-lite"`, siehe bestehende Router als
Beispiel), f-Strings statt `.format()`/`%`. `Enum` für geschlossene
Wertemengen (siehe `app/models/common.py` - `ItemStatus`, `UserRole`,
`AuthSource`), nicht lose Strings, die überall im Code neu getippt werden
müssten.

## Linting

`ruff check .` - lokal, **läuft nicht in der CI** (bewusst zurückgestellt,
siehe `ruff.toml`-Kommentar). Vor größeren Änderungen trotzdem laufen
lassen. Konfiguration: `E`/`F`/`W`/`B` (pycodestyle, pyflakes,
flake8-bugbear), `E501` (Zeilenlänge) bewusst ignoriert - das Projekt hält
zusammengehörige Route-Definitionen/Query-Chains/erklärende Kommentare
bewusst in einer Zeile, ein Zeilenlängen-Limit würde das nur bestrafen.
Alembic-Migrationen sind von `F401`/`F841` ausgenommen (generiertes
Boilerplate, an gelaufenen Migrationen wird nichts mehr geändert).

## FastAPI-Spezifika

`Depends(...)`/`Form(...)`/`Query(...)` etc. im Funktions-Default ist
beabsichtigtes Framework-Pattern (FastAPI wertet das pro Request neu aus),
kein B008-Mutable-Default-Verstoß - siehe `extend-immutable-calls` in
`ruff.toml`. Bei neuen FastAPI-Aufrufmustern, die Ruff fälschlich als
Fehler markiert, dort ergänzen statt die Regel projektweit abzuschalten.

## Fehlerbehandlung

Keine bare `except:`. Exceptions spezifisch fangen, loggen (Ursache,
relevante IDs, keine sensiblen Daten - siehe `docs/security/secrets.md`),
und wo sinnvoll in eine für den Nutzer verständliche Fehlermeldung
übersetzen statt einen Stacktrace/500 durchzureichen. Beispielmuster:
`app/core/uploads.py::_process_and_save_sync` fängt Pillow-spezifische
Exceptions und wirft eine eigene `InvalidImage` mit klarer Meldung.

## Größenrichtwerte

Ca. 40 Zeilen pro Funktion, ca. 500 Zeilen pro Datei (siehe `CLAUDE.md`).
Wird eine Datei deutlich größer, zuerst nach fachlicher Kohäsion trennen
(siehe `docs/architecture/backend.md`), nicht nach technischer Schicht.

## Async

`async`/`await` durchgängig im Request-Pfad. Blockierende/CPU-lastige
Arbeit explizit über `run_in_threadpool` auslagern (siehe
`docs/architecture/backend.md`) statt sie synchron im Event-Loop laufen
zu lassen.
