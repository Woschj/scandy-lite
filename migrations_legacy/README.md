# Legacy-Migration (Scandy2 / MongoDB → Scandy-Lite / PostgreSQL)

**Status: nicht priorisiert, noch nicht implementiert.**

Dieser Ordner ist ein Platzhalter für ein späteres Migrationsskript, das
Bestandsdaten aus der alten MongoDB-Instanz (Scandy2) in dieses PostgreSQL-Schema
überführt.

## Geplanter Ansatz (grob, wenn es soweit ist)

1. Read-only-Export aus MongoDB pro Collection (`tools`, `workers`, `consumables`,
   `lendings`, `users`) als JSON/BSON-Dump.
2. Mapping-Tabelle alte Mongo-`ObjectId` → neue Postgres-`UUID` pro Entität,
   damit Fremdschlüssel-Beziehungen (z.B. Lending → Tool/Worker) korrekt
   übersetzt werden.
3. Abteilungen (`department`-Freitext-Feld in Scandy2) zunächst einmalig zu
   sauberen `Department`-Datensätzen normalisieren (Scandy2 hatte keine eigene
   Department-Tabelle, nur ein String-Feld auf jedem Dokument).
4. Datenqualitäts-Checks vor dem Import: Scandy2 hatte offenbar bekannte
   Inkonsistenzen zwischen Tool-Status und offenen Lendings
   (`validate_lending_consistency` / `fix_lending_inconsistencies` existierten
   dort als Reparatur-Funktionen) - diese Fälle müssen beim Import erkannt und
   bereinigt werden, nicht 1:1 übernommen.
5. Idempotentes Import-Skript (mehrfach ausführbar ohne Duplikate), inkl.
   Trockenlauf-Modus (`--dry-run`) vor dem eigentlichen Import.

## Nicht jetzt bauen

Das ergibt erst Sinn, wenn das neue Schema (Phase 1-4) stabil ist und Scandy-Lite
tatsächlich produktiv abgelöst werden soll. Bis dahin bleibt dieser Ordner leer.
