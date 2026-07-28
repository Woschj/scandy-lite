# Namenskonventionen

## Tabellen &amp; Modelle

SQLModel-Konvention, durchgängig eingehalten: **Tabellennamen Plural,
Modell-Klassennamen Singular** (`items` ↔ `Item`, `departments` ↔
`Department`, `user_department_roles` ↔ `UserDepartmentRole`). Spalten
`snake_case`.

## Bewusste Namensentscheidung: `Item`, nicht `Tool`

Die Kern-Entität heißt `Item`/`items`, nicht `Tool`/`tools` - "Gegenstand"
ist neutraler als "Werkzeug", nicht jede Abteilung, die Scandy-Lite nutzt,
leiht zwangsläufig Werkzeuge aus (z. B. Büro-Abteilungen). Bei neuen
Feldern/Funktionen an diesem Namen orientieren, nicht "Tool" wieder
einführen.

## Wiederkehrende Muster

- **Soft-Delete:** `deleted_at: datetime | None` (`SoftDeleteMixin`) statt
  eines Booleans - erlaubt Papierkorb + Zeitpunkt in einem Feld.
- **Zeitstempel:** `created_at`/`updated_at` (`TimestampMixin`) auf jeder
  Tabelle, die das braucht - kein Modell erfindet eigene Namen dafür
  (nicht `date_created`, nicht `modified_at`).
- **Primärschlüssel:** `id: uuid.UUID` über `new_uuid()` - keine
  Auto-Increment-Integer-IDs. UUIDs sind über Tabellen hinweg eindeutig,
  wichtig für die Legacy-Migration aus Scandy2 und den Papierkorb-
  Snapshot-Mechanismus (siehe `docs/database/migrations.md`).
- **"Eine Quelle der Wahrheit" statt Status-Feld-Sync:** ob ein Gegenstand
  ausgeliehen ist, ergibt sich aus `Lending.returned_at IS NULL`, nicht aus
  einem separaten, manuell zu pflegenden `status`-Feld auf `Item` (Item hat
  zwar ein `status`-Feld, das aber synchron zur Lending-Zeile gehalten wird,
  nie unabhängig davon). Gleiches Prinzip bei Reservierungen
  (`fulfilled_at`/`cancelled_at`).
- **Snapshot-Spalten:** wo ein Fremdschlüssel nach dem Löschen der
  referenzierten Entität `NULL` werden kann, existiert eine begleitende
  `..._name_snapshot`/`..._barcode_snapshot`-Textspalte (siehe
  `app/models/lending.py`, `app/models/reservation.py`) - Namenskonvention:
  `<entität>_<feld>_snapshot`.

## Neue Modelle

Vor dem Anlegen eines neuen Modells: passt es in dieses Muster (Plural-
Tabelle/Singular-Klasse, UUID-PK, Timestamp-/SoftDelete-Mixins wo
sinnvoll)? Abweichungen brauchen einen Kommentar, der erklärt, warum
(siehe `CLAUDE.md` "Kommentare erklären WARUM").
