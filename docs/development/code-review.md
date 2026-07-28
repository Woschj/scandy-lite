# Code Review

Gilt sowohl für Reviews an fremdem Code als auch als Selbst-Check vor
Abschluss einer eigenen Änderung (siehe `CLAUDE.md` "Arbeitsweise" - letzter
Schritt: abschließend selbst Code Review durchführen).

## Prüf-Reihenfolge (nach Priorität, siehe `CLAUDE.md`)

1. **Korrektheit** - macht der Code, was er soll, inklusive Edge Cases
   (leere Liste, gelöschte referenzierte Entität, gleichzeitiger Zugriff)?
2. **Sicherheit** - siehe `docs/security/owasp.md`-Checkliste: neue
   Nutzereingabe validiert? Neue Route mit korrekter
   Berechtigungsprüfung (`require_staff`/`require_admin`/
   `is_staff_in_department`)? CSRF-Token bei neuem Formular?
3. **Wartbarkeit/Architektur** - passt die Änderung zu
   `docs/architecture/backend.md`/`frontend.md` (Schichtung, Namens-
   konventionen aus `docs/database/naming.md`)? Wurde eine bestehende
   Abstraktion wiederverwendet, wo sie existiert (z. B.
   `inventory_crud.py`), statt Logik zu duplizieren?
4. **Performance** - neue N+1-Query? Fehlender Index für ein neues
   Filterfeld (siehe `docs/database/indexing.md`)?
5. **Tests** - deckt ein Test den neuen/geänderten Pfad ab (siehe
   `docs/development/testing.md`)? Wurde ein gemeldeter Bug mit einem
   Test abgesichert, der ohne den Fix fehlschlägt?
6. **Dokumentation** - `README.md`/`CHANGELOG.md`/betroffene `docs/`-
   Datei aktualisiert, falls sich Verhalten/Architektur geändert hat?
7. **Nebeneffekte** - wirkt sich die Änderung auf Migrationen,
   Cache-Busting (`app/version.py`, siehe
   `docs/roadmap/technical-debt.md`), oder bestehende Templates aus, die
   dieselbe CSS-Klasse/denselben Helper nutzen?

## Bei gefundenen Bugs

Nicht nur den einzelnen Fehler beheben. Prüfen: warum konnte er
entstehen, kann dieselbe Fehlerklasse an anderen Stellen im Code
auftreten (z. B. dieselbe Browser-Kompatibilitätsfalle in einem anderen
Template), sollte die Architektur an der Stelle angepasst werden, damit
diese Fehlerklasse strukturell ausgeschlossen ist? Konkretes Beispiel aus
diesem Projekt: der Safari-`<details>`-Bug (`CHANGELOG.md` 0.23.1) wurde
nicht nur an der einen Stelle gefixt, sondern das zugrunde liegende Muster
("`<details>` nie mit einer bestehenden flexbasierten Zeilen-Klasse
kombinieren") als Lektion in `docs/architecture/frontend.md` festgehalten.

## Was ein Review NICHT tun sollte

Keine unnötigen Großumbauten "weil man schon dabei ist" durchwinken -
kleine Refactorings (bessere Namen, toter Code raus) sind erwünscht, ein
Umbau der Architektur gehört in eine eigene, separat besprochene Änderung
(siehe `CLAUDE.md` "Arbeitsweise").
