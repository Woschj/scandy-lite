# Legacy-Migration (Scandy2 / MongoDB → Scandy-Lite / PostgreSQL)

Migriert Bestandsdaten aus der alten MongoDB-Instanz (Scandy2) nach Scandy-Lite.
Read-only auf MongoDB-Seite - es wird dort nichts verändert oder gelöscht.

## Was migriert wird

| Scandy2 (MongoDB) | Scandy-Lite (PostgreSQL) | Hinweise |
|---|---|---|
| `department`-Freitextfeld (+ `settings.departments`) | `Department` | Namen dedupliziert, Code automatisch generiert (Umlaute transkribiert) |
| `settings.categories` / `settings.locations` | `Category` / `Location` | Abteilungsbezogen, wo im Original vorhanden |
| `tools` | `Item` | `status` wird NICHT blind übernommen - echter Status wird aus offenen `lendings` neu abgeleitet |
| `consumables` | `Consumable` | `unit` gab's im Original nicht → Default "Stück" |
| `workers` | `Worker` | Verknüpfung zum migrierten `User` über `username`, falls vorhanden |
| `lendings` | `Lending` | Referenzierung im Original über Barcode, nicht ID - wird aufgelöst |
| `consumable_usages` | `ConsumableUsage` | Nur echte Entnahmen (negative Menge, echter Mitarbeiter) - Nachschub-Buchungen haben in Scandy-Lite kein Log-Äquivalent |
| `users` | `User` | Rollen-Mapping: `admin`→Admin, `anwender`→Mitarbeiter, `teilnehmer`→Nutzer. **Passwörter können nicht migriert werden** (anderes Hash-Verfahren) - jeder User bekommt ein neues Zufallspasswort |

**Nicht migriert** (bewusst, deckt sich mit dem ursprünglichen Scope-Schnitt von
Scandy-Lite): Tickets, Kantinenplan, Jobs, Custom Fields, Feature-Flags,
Notification-Center, `user_groups`-Software-Zuordnung.

## Nutzung

```bash
pip install -r migrations_legacy/requirements.txt

# 1. Trockenlauf - zeigt nur einen Report, schreibt nichts
python -m migrations_legacy.migrate_from_mongodb \
  --mongo-uri "mongodb://user:passwort@host:27017" --mongo-db scandy

# 2. Report plausibel? Dann wirklich schreiben:
python -m migrations_legacy.migrate_from_mongodb \
  --mongo-uri "mongodb://user:passwort@host:27017" --mongo-db scandy --apply
```

Danach liegt eine `migration_passwords.txt` mit den neu generierten Passwörtern
für alle migrierten Benutzer im aktuellen Verzeichnis - sicher verteilen und
**danach löschen**.

**Idempotent:** Das Skript lässt sich gefahrlos mehrfach mit `--apply` ausführen
(z.B. nach einem Abbruch oder um neue Daten aus Mongo nachzuziehen) - bereits
migrierte Datensätze werden über Barcode bzw. Kombination erkannt und
übersprungen, nichts wird doppelt angelegt.

## Architektur des Skripts

Bewusst in zwei Schichten getrennt:

- **`transform.py`** - reine Übersetzungsfunktionen (Mongo-dict → Scandy-Lite-Felder),
  ohne jeden DB-Zugriff. Vollständig isoliert testbar.
- **`migrate_core.py`** - die eigentliche Schreiblogik (Duplikat-Erkennung,
  Referenzauflösung, Statusableitung), nimmt bereits gelesene Python-Daten
  entgegen statt selbst mit MongoDB zu sprechen. Dadurch mit synthetischen
  Testdaten gegen eine echte (SQLite-)Datenbank durchspielbar.
- **`migrate_from_mongodb.py`** - dünner CLI-Wrapper: verbindet zu MongoDB,
  liest die Collections roh ein, reicht sie an `migrate_core.migrate()` weiter.

Getestet (`python migrations_legacy/test_*.py`, kein Mongo/Postgres nötig):
- `test_transform.py` - 32 Checks der reinen Übersetzungslogik
- `test_migrate.py` - kompletter Schreib-Durchlauf inkl. Duplikat-/Referenz-
  Behandlung gegen SQLite, inkl. zweitem Lauf zur Idempotenz-Prüfung
- `test_fetch_mongo.py` - MongoDB-Lese-Schicht gegen `mongomock` (In-Memory-Mongo)

**Nicht getestet werden konnte:** eine echte Verbindung zu eurer tatsächlichen
Scandy2-MongoDB-Instanz (in der Sandbox-Umgebung nicht erreichbar) - die
Feldnamen/Strukturen basieren auf Analyse des Scandy2-Quellcodes, nicht auf
einem Live-Datenabgleich. **Bitte zuerst den Trockenlauf gegen eure echten
Daten laufen lassen und den Report genau prüfen, bevor `--apply` verwendet wird.**
