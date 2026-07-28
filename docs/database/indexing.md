# Indizierung

Grundregel: **jede Spalte, nach der gefiltert, gesucht oder sortiert wird,
bekommt einen Index** - `Field(index=True)` in SQLModel, nicht nachträglich
per Hand in einer Migration vergessen.

## Aktueller Stand (Beispiele)

- `Item.barcode` / `Consumable.barcode` - indiziert, zusätzlich ein
  **partieller Unique-Index** nur auf aktive (nicht soft-gelöschte)
  Datensätze (siehe Migration `45dd75eab85a`). Ein normaler Unique-Index
  auf `barcode` allein würde verhindern, dass ein neuer Gegenstand denselben
  Barcode wie ein bereits gelöschter bekommt.
- `Item.category` / `Item.location` - indiziert (Filter-Dropdowns in der
  Listenansicht, Autocomplete-Vorschläge).
- `*.department_id` (Items, Consumables, Lendings, Reservations, ...) -
  jede Fremdschlüsselspalte, die zur Abteilungs-Sichtbarkeitsprüfung
  gehört (`app/core/access.py`), ist indiziert - diese Prüfung läuft bei
  praktisch jedem Request.
- `Lending.returned_at` / `Reservation.fulfilled_at`+`cancelled_at` - keine
  eigenen Indizes bisher, aber Kandidaten, sobald die Historie einer
  Abteilung groß wird (Filterung auf "noch offen" per `IS NULL`).

## Vorgehen bei neuen Spalten

Vor dem Hinzufügen einer neuen Filterspalte kurz überlegen: wird danach in
einer `WHERE`- oder `ORDER BY`-Klausel gefiltert/sortiert, die bei
wachsender Tabellengröße relevant wird? Wenn ja, Index gleich in derselben
Migration mitgeben, nicht als Nachtrag "wenn's mal langsam wird" - ein
fehlender Index fällt in der Entwicklung mit wenigen Testdatensätzen nie
auf, erst bei echten Datenmengen.

## N+1-Vermeidung

Kein Index-Problem im engeren Sinn, aber verwandt: `selectinload(...)` für
Beziehungen konsequent nutzen, die im selben Request gebraucht werden
(siehe z. B. `app/routers/pickup.py::get_open_reservations_for_worker`,
das `Reservation.item` eager lädt statt pro Zeile nachzuladen). Ein
bekannter, bereits behobener Fall: Zusatzfelder wurden früher pro
Gegenstand einzeln nachgeladen (siehe `CHANGELOG.md`, "N+1-Fix bei
Zusatzfeldern").
