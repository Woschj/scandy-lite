# Scandy-Lite Development Guide

> Dieses Dokument definiert die Entwicklungsrichtlinien für alle AI-Agents,
> insbesondere Claude Code, auf diesem Projekt.
>
> Ziel ist es, Scandy-Lite langfristig auf Enterprise-Niveau zu entwickeln.
> Bei Konflikten zwischen Geschwindigkeit und Qualität gewinnt immer Qualität.
>
> Details zu einzelnen Themen (Architektur, Security-Stand, DB-Konventionen,
> Testing, Docker, Design-System, Roadmap) liegen in `docs/` - siehe
> Übersicht am Ende dieser Datei. Diese Datei bleibt bewusst der kompakte
> Einstiegspunkt mit Priorität/Arbeitsweise; Details gehören in `docs/`
> statt hier dupliziert zu werden.

---

# Projektvision & aktueller Scope

Langfristige Vision: eine moderne Open-Source-Lösung für IT Asset
Management, Inventarisierung und Dokumentation (Softwareverwaltung,
Netzwerkdokumentation, Lizenzmanagement, Plugin-System, Discovery,
Mandantenfähigkeit, LDAP/SAML, GraphQL, ...).

**Das ist keine aktuelle Beauftragung.** Der tatsächliche Scope der App ist
heute auf Ausleihe-/Ausgabe-Verwaltung für Werkzeuge und Verbrauchsmaterial
begrenzt (Datenmodell, Auth + Abteilungs-Rollenmodell, Quickscan,
Sammel-Abholung, Reservierungen, Historie, Papierkorb - siehe
`docs/roadmap/roadmap.md` für den laufend gepflegten Ist-Stand). Punkte wie
Discovery oder ein Plugin-System sind bewusst NICHT umgesetzt und nicht
geplant, solange nicht explizit anders entschieden wird - siehe
`docs/architecture/discovery.md` und `docs/architecture/plugin-system.md`.

Eine Vision-Nennung hier ist also **kein fehlendes Feature, das nachgeholt
werden soll**. Neue Funktionen bewegen sich innerhalb des aktuellen Scopes,
es sei denn, der Projektverantwortliche beauftragt explizit einen
Vision-Punkt.

---

# Grundprinzip & Rolle

Handle wie ein erfahrener Softwarearchitekt: nicht "wie bekomme ich das
schnell zum Laufen?", sondern "wie sollte dieses Projekt in fünf Jahren
aussehen?". Denke dabei gleichzeitig aus der Perspektive von Senior
Python/Fullstack Engineer, DevOps, Security Engineer, Software Architect
und Code Reviewer.

---

# Entwicklungsprinzipien

Priorität, wenn Ziele konkurrieren:

1. Korrektheit
2. Sicherheit
3. Wartbarkeit
4. Lesbarkeit
5. Testbarkeit
6. Performance
7. Neue Features

Neue Features dürfen niemals die Architektur verschlechtern. Bei mehreren
möglichen Lösungen dieselbe Reihenfolge: Einfachheit vor Wartbarkeit vor
Testbarkeit vor Erweiterbarkeit vor Performance - nicht umgekehrt.

---

# Arbeitsweise

Für jede Aufgabe:

1. Problem vollständig analysieren, betroffene Komponenten identifizieren
   (Router, Model, Template, Migration?).
2. Beste Lösung auswählen, Auswirkungen/Risiken bewerten - erst danach
   implementieren. Keine vorschnellen Änderungen.
3. Implementieren. Kleine Refactorings an berührtem Code sind erlaubt
   (bessere Namen, toter Code raus, Duplikate raus) - keine unnötigen
   Großumbauten "weil man schon dabei ist".
4. Danach prüfen: Kann etwas kaputtgehen? Seiteneffekte? Migration nötig?
   Tests/Dokumentation anzupassen?
5. Tests prüfen/ergänzen, Dokumentation aktualisieren (README, CHANGELOG,
   betroffene `docs/`-Datei).
6. Abschließend selbst Code Review durchführen - siehe
   `docs/development/code-review.md` für die vollständige Checkliste
   (Korrektheit, Sicherheit, Wartbarkeit, Performance, Tests, Doku,
   Nebeneffekte, in dieser Reihenfolge).

## Wenn Bugs gefunden werden

Nicht nur den einzelnen Fehler beheben. Auch prüfen: Warum konnte er
entstehen? Kann dieselbe Fehlerklasse an anderen Stellen auftreten? Sollte
die Architektur angepasst werden, damit sie strukturell ausgeschlossen ist?
(Konkretes Vorgehen/Beispiel: `docs/development/code-review.md`.)

Dasselbe gilt für erkannte technische Schulden/bewusste Abkürzungen, nicht
nur für Bugs - siehe `docs/roadmap/technical-debt.md` zum Eintragen statt
unkommentiert im Code zu lassen.

---

# Architektur

Bevorzuge lose Kopplung, hohe Kohäsion, Dependency Injection, kleine
Module, Single Responsibility, Composition over Inheritance. Vermeide God
Classes, Utility-Monster, globale Zustände, zyklische Abhängigkeiten,
unnötige Komplexität.

Richtwerte: ca. 40 Zeilen pro Funktion, ca. 500 Zeilen pro Datei (Code -
für `docs/`-Markdown gilt dieses Limit nicht). Große Dateien nach
fachlicher Kohäsion aufteilen, nicht nach technischer Schicht - siehe
`docs/architecture/backend.md` (Schichtung, DI) und
`docs/architecture/frontend.md` (Templates/JS/CSS-Struktur) für den
projektspezifischen Ist-Stand.

---

# Python

Type Hints, `pathlib`, `logging` statt `print()`, `Enum` für geschlossene
Wertemengen, f-Strings, `async`/`await` durchgängig im Request-Pfad. Keine
bare `except:`, jeder Fehler spezifisch gefangen, geloggt (Ursache,
relevante IDs, keine sensiblen Daten), verständlich. Keine globalen
Variablen, keine tief verschachtelten if-Blöcke, keine langen Funktionen.

Projektspezifische Details (Linting/`ruff.toml`, FastAPI-`Depends`-Pattern,
Async-Offloading) siehe `docs/development/python.md`.

---

# Datenbank

PostgreSQL (SQLite nur in Tests). Keine unnötigen `SELECT *`, Indizes für
jede gefilterte/sortierte Spalte, Foreign Keys beachten, Transaktionen
korrekt verwenden, keine Breaking Changes ohne Migration. Details/
Namenskonventionen/Stolperfallen: `docs/database/migrations.md`,
`docs/database/naming.md`, `docs/database/indexing.md`.

---

# Docker

Container klein, reproduzierbar, mit Healthcheck, non-root, Secrets nie im
Image, Konfiguration über ENV-Variablen. Details zum aktuellen Stack
(Multi-Stage-Build, Compose-Dateien, Entrypoint): `docs/development/docker.md`.

---

# Sicherheit

Bei jeder Änderung, die Nutzereingaben, Auth oder Dateizugriff berührt,
immer prüfen auf: SQL Injection, XSS, CSRF, Path Traversal, Command
Injection, SSRF, Broken Authentication, Hardcoded Secrets, unsichere
Dateiberechtigungen.

Projektspezifischer Absicherungs-Stand inkl. bewusst dokumentierter
bekannter Lücken: `docs/security/owasp.md`. Secrets-Handling (Env-Vars vs.
Docker-Secrets, Fail-Fast in Produktion, Bild-Upload-Härtung):
`docs/security/secrets.md`. Auth-/Session-/Rollenmodell:
`docs/architecture/auth.md`.

---

# API

APIs sollen konsistent und REST-konform sein, sinnvolle Statuscodes
liefern, validierte Eingaben besitzen, Fehlermeldungen standardisieren.

---

# Frontend

UI soll modern, übersichtlich, responsive, zugänglich sein. Keine
unnötigen Frameworks einführen. Design-System (Tag-Card-Motiv, CSS Custom
Properties, kein Dark Mode implementiert): `docs/design/ui.md`. Formulare
(CSRF, `fv`-Fehleranzeige, Scanner-Eingabe): `docs/design/forms.md`.
Listen/Tabellen (Karten statt `<table>`, keine Bulk-Aktionen):
`docs/design/tables.md`. JS-Modul-/CSS-Struktur:
`docs/architecture/frontend.md`.

---

# Performance

Vor Änderungen überlegen: Kann diese Funktion häufig aufgerufen werden?
Gibt es N+1-Queries? Fehlt ein Index für ein neues Filterfeld (siehe
`docs/database/indexing.md`)? Kann gecacht/lazy geladen werden?
Optimierungen nur bei tatsächlichem Nutzen.

---

# Tests

Welche Tests fehlen, welche Edge Cases gibt es, kann etwas regressieren -
bei jeder Änderung überlegen, bei Bedarf Unit-/Integrationstests ergänzen.
Werkzeuge, Grundmuster (echte HTTP-Roundtrips statt reiner Unit-Tests),
SQLite-Fallstricke in Tests: `docs/development/testing.md`.

---

# Dokumentation

Bei Änderungen prüfen, ob README, CHANGELOG, Migrationen oder eine
betroffene `docs/`-Datei aktualisiert werden müssen (siehe Übersicht unten).
Veraltete Doku ist schlimmer als keine - lieber eine `docs/`-Datei knapp
halten als sie von der Realität abweichen lassen.

---

# Kommentare

Kommentare erklären WARUM, nicht WAS der Code macht.

---

# Git

Commits sollen klein, verständlich, atomar sein. Keine riesigen
Sammeländerungen.

---

# Abhängigkeiten

Neue Bibliotheken nur wenn aktiv gepflegt, gut dokumentiert, weit
verbreitet, Sicherheitsrisiko gering. Lieber vorhandene Bibliotheken
nutzen.

---

# Was vermieden werden soll

Keine Quick Fixes ohne Root-Cause-Analyse. Keine TODOs ohne Begründung.
Keine doppelte Logik/Copy&Paste-Lösungen. Keine Magic Numbers, Hardcoded
URLs/Ports/Passwörter. Keine unnötigen Dependencies oder Komplexität -
insbesondere kein Vorbau für Vision-Punkte aus "Projektvision & aktueller
Scope", die nicht beauftragt sind.

---

# Übersicht: docs/

Detailwissen lebt hier, nicht in dieser Datei - bei Bedarf lesen statt aus
dem Training zu raten, da projektspezifisch verifiziert:

| Bereich | Dateien |
|---|---|
| Architektur | `docs/architecture/backend.md`, `frontend.md`, `auth.md`, `discovery.md` (Scope-Klarstellung), `plugin-system.md` (Scope-Klarstellung) |
| Datenbank | `docs/database/migrations.md`, `naming.md`, `indexing.md` |
| Design | `docs/design/ui.md`, `forms.md`, `tables.md` |
| Entwicklung | `docs/development/python.md`, `testing.md`, `docker.md`, `code-review.md` |
| Sicherheit | `docs/security/owasp.md`, `secrets.md` |
| Roadmap | `docs/roadmap/roadmap.md` (Ist-Stand/Scope), `technical-debt.md` (bewusste Kompromisse) |

Neue projektspezifische Erkenntnisse (Stolperfalle, bewusste
Design-Entscheidung, technische Schuld) gehören in die passende
`docs/`-Datei, nicht als Wissen, das nur im Gesprächsverlauf existiert.

---

# Abschluss

Nicht einfach Code erzeugen. Verbessere das Projekt. Jede Änderung soll
Scandy-Lite näher an eine professionelle Open-Source-Lösung auf
Enterprise-Niveau bringen - innerhalb des aktuellen Scopes (siehe oben).
Bei Unsicherheiten zuerst bestehenden Code und `docs/` analysieren, bevor
neue Strukturen eingeführt werden.
