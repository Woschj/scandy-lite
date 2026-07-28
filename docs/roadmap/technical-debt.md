# Technische Schulden

Bewusst dokumentierte Kompromisse - nicht "vergessen aufzuräumen", sondern
Entscheidungen, die bei wachsendem Bedarf neu bewertet werden sollten.
Neue Einträge hier ergänzen, statt sie nur im Kopf zu behalten oder als
Code-Kommentar verstreuen zu lassen (siehe `CLAUDE.md` "Wenn Bugs gefunden
werden" - dieselbe Denkweise gilt für erkannte strukturelle Schwächen,
nicht nur für Bugs).

## Manuelles Cache-Busting

`asset_version` (`app/version.py::__version__`) muss bei jeder CSS/JS-
relevanten Änderung von Hand mitgezogen werden - vergisst man das, bleiben
Browser mit bereits gecachtem `app.css`/JS auf altem Stand (real passiert,
siehe `CHANGELOG.md` 0.23.0/0.23.1). Ein inhaltsbasierter Hash
(`app.css?v=<sha256-prefix-des-dateiinhalts>`) würde diese Fehlerklasse
strukturell ausschließen. Aufwand/Nutzen bisher nicht als hoch genug
bewertet, um das umzubauen - bei einer weiteren Wiederholung des Problems
neu bewerten.

## Ein einziges CSS-File

`app/static/css/app.css` wächst mit jedem Feature (Stand: über 2000
Zeilen). Funktioniert bisher gut mit Kommentar-Abschnitten als grobe
Gliederung, aber die Datei sprengt langfristig die "ca. 500 Zeilen"-
Richtgröße aus `CLAUDE.md` deutlich. Aufteilen (z. B. nach Bereich:
`base.css`, `forms.css`, `settings.css`, ...) erst, wenn das Navigieren in
der Datei selbst zum Problem wird - vorher würde die Aufteilung nur neue
Import-Reihenfolge-Fallstricke einführen (Kaskade!), ohne echten Nutzen.

## Kein geteilter Rate-Limit-Store

Login-/Passwort-Reset-Rate-Limiting ist In-Memory pro Prozess (siehe
`docs/architecture/auth.md`). Läuft die App je einmal auf mehreren
Instanzen hinter einem Load Balancer, zählt jede Instanz unabhängig -
das Limit greift dann effektiv erst bei einem Vielfachen der
konfigurierten Versuche. Aktuell kein Problem (ein Container pro
Deployment), relevant erst bei horizontaler Skalierung.

## Kein Security-Scanning in der CI

Siehe `docs/security/owasp.md`. `pip-audit`/`safety`/vergleichbares Tool
als CI-Schritt wäre ein sinnvoller, kleiner nächster Schritt.

## Keine Repository-/Service-Schicht

Siehe `docs/architecture/backend.md`. Bewusst so belassen, solange Router
überschaubar bleiben - wird ein Router-File wiederholt zu groß/zu
verzweigt, ist das ein Signal, fachliche Logik in ein eigenes Modul
auszulagern (wie bereits bei `app/core/inventory_crud.py` geschehen),
nicht sofort eine generische Schichtenarchitektur einzuführen.

## Neue Einträge

Beim Entdecken einer bewussten Abkürzung/eines Kompromisses während der
Arbeit: hier eintragen (Was, Warum, wann neu bewerten), statt es
unkommentiert im Code zu lassen.
