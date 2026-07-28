# Migrationen

Alembic ist der einzige Weg, das Schema zu ändern - kein manuelles
`ALTER TABLE`, kein `Base.metadata.create_all()` in Produktion. Aktuell 19
Migrationen unter `alembic/versions/`.

## Ablauf

1. Modell in `app/models/*.py` ändern.
2. `alembic revision --autogenerate -m "kurze beschreibung"`.
3. **Generierte Migration immer lesen, nicht blind vertrauen** -
   Autogenerate erkennt z. B. keine Umbenennungen (macht daraus
   drop+add und verliert Daten) und keine Enum-Wert-Änderungen zuverlässig.
4. Gegen eine echte Postgres-Instanz testen, nicht nur gegen SQLite (siehe
   `docs/development/testing.md` - SQLite verdeckt reale FK-/Enum-Bugs).
5. `alembic upgrade head` lokal verifizieren, danach `alembic downgrade -1`
   testen, falls die Migration im Fehlerfall zurückgerollt werden können
   soll.

Im Container wendet `docker/entrypoint.sh` `alembic upgrade head`
automatisch bei jedem Start an - kein manueller Schritt bei einem Deploy.

## Zwei projektspezifische Stolperfallen

- **`transaction_per_migration=True`** ist in `alembic/env.py` gesetzt.
  Ohne das laufen bei einem frischen Deployment ALLE ausstehenden
  Migrationen in einer einzigen Transaktion - `ALTER TYPE ... ADD VALUE`
  gefolgt von sofortiger Nutzung des neuen Enum-Werts in derselben Sitzung
  scheitert dann mit "unsafe use of new value" (Postgres-Regel: neue
  Enum-Werte sind erst nach COMMIT nutzbar).
- **Enum-Typen, die eine SPÄTERE Migration wiederverwendet**, brauchen dort
  `create_type=False` (Beispiel:
  `980f814ad082_user_department_roles_replace_worker_...py`) - sonst
  versucht Alembic, denselben Postgres-Enum-Typ ein zweites Mal
  anzulegen, was fehlschlägt. Nur die Migration, die den Typ ursprünglich
  erzeugt, lässt `create_type` auf dem Default (`True`).

## Datenerhalt beim Löschen

Migrationen, die Fremdschlüssel auf potenziell gelöschte Entitäten
betreffen (Items, Consumables, User), müssen den in
`app/core/trash.py` beschriebenen Snapshot-Mechanismus respektieren:
abgeschlossene Historien-Zeilen behalten Name/Barcode als Text, nur die
FK-Spalte wird `NULL`. Eine Migration, die diese Snapshot-Spalten entfernt
oder NOT NULL erzwingt, würde diesen Mechanismus brechen.
