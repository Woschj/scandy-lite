# Changelog

Alle nennenswerten Änderungen an Scandy-Lite werden hier dokumentiert.

Format angelehnt an [Keep a Changelog](https://keepachangelog.com/de/1.1.0/),
Versionierung nach [Semantic Versioning](https://semver.org/lang/de/) (vor
1.0.0: `0.MINOR.PATCH`, MINOR kann auch für neue Features brechende Änderungen
enthalten - üblich für Software vor dem ersten stabilen Release).

> Die Einträge bis 0.8.0 wurden rückwirkend aus der Commit-Historie
> rekonstruiert (das Projekt hatte bis Version 0.9.0 keine Versionsnummer) -
> Datumsangaben sind die des jeweils letzten Commits im Zeitraum, Gruppierung
> orientiert sich an zusammenhängenden Arbeits-Sessions statt an einzelnen
> Commits.

## [0.9.0] - 2026-07-17

### Changed
- Item/Consumable-CRUD-Duplizierung aufgelöst: `app/core/inventory_crud.py`
  bündelt Presets-Auflösung sowie Löschen/Bild-Upload/Bild-Löschen für beide
  Typen, Router sind jetzt dünne Wrapper. Gleiches Prinzip für die
  Papierkorb-Routen in `admin_settings.py` (jetzt inkl. Benutzer über
  dieselbe Konfiguration).
- `purge_department` (app/core/trash.py) entschlackt: der dreifach
  wiederholte Force/Block-Block für offene Ausleihen/Reservierungen/
  Material-Vormerkungen ist jetzt ein einziger Helper (`_close_open_or_block`).
- `migrations_legacy/migrate_core.py`: `migrate()` (vorher 341 Zeilen, eine
  Funktion) in acht benannte Teilschritte aufgeteilt (Abteilungen, Presets,
  Benutzer, Mitarbeiter-Ausweise, Gegenstände, Verbrauchsmaterial, Ausleihen,
  Entnahmen) - Verhalten unverändert, per Regressionslauf gegen
  `test_migrate.py`/`test_fetch_mongo.py` verifiziert.

### Added
- Versionsnummer (`app/version.py`, sichtbar unter Einstellungen) und dieses
  Changelog.

## [0.8.0] - 2026-07-16 – 2026-07-17

### Added
- Abteilungen können kaskadierend gelöscht werden (Gegenstände/Material/
  Mitarbeiter werden mitgelöscht, Historie bleibt als Text-Schnappschuss
  erhalten); Force-Löschen schließt offene Ausleihen/Reservierungen/
  Vormerkungen dabei automatisch ab, statt den Vorgang zu blockieren.

### Changed
- Mac-Style-Buttons, Hamburger-Navigation, klarere Detail-Karten.
- Historie-Suche findet jetzt auch Barcodes, nicht nur Namen.

### Fixed
- `purge_department` nannte bei offener Ausleihe/Reservierung keine Namen.
- Überlappender Text bei vielen Chips; Schriftart durchgängig auf
  Trebuchet MS vereinheitlicht.

### Docs
- README auf aktuellen Stand gebracht (Worker/User-Merge, Löschverhalten).

## [0.7.0] - 2026-07-14

### Changed
- **User und Worker zu einer Entität vereinheitlicht** (Mitarbeiter-Ausweis
  und Login sind seither derselbe Datensatz statt zweier verknüpfter
  Zeilen) - größter Datenmodell-Umbau seit Projektstart.

### Fixed
- Migration `b6f1c9a4d2e7` nutzte einen falschen Enum-Wert für `auth_source`.
- Migration `b6f1c9a4d2e7` hing Fremdschlüssel-Constraints in falscher
  Reihenfolge um.

## [0.6.0] - 2026-07-13

### Added
- SMTP-Konto (Admin-UI) + Passwort-Reset + Willkommens-Mail.
- Login- und Mitarbeiter-Stammdaten auf einer Seite bearbeitbar.
- Echte Custom Fields für Gegenstände, pro Kategorie konfigurierbar.
- Papierkorb für gelöschte Gegenstände/Material/Mitarbeiter.

### Changed
- Docker-Build-Cache optimiert; N+1-Query-Fix bei Zusatzfeldern;
  Lösch-Fehlermeldungen nennen jetzt Namen statt nur "es gibt noch offene …".

### Fixed
- Custom-Field-Enum-Typ in Postgres; schiefes Einstellungen-Layout;
  Kategorie-/Standort-Dropdown beim Anlegen; Verbrauchsmaterial-Dropdown;
  Checkboxen in Einstellungen-Formularen erzwangen eigene volle Zeile.
- 9 Funde aus einem breiten Code-Review behoben.
- Mobile-Darstellungsfehler aus Screenshots behoben.
- Worker/User-Verknüpfung erzeugte einen doppelten Ausweis-Datensatz.
- entrypoint.sh: Zeilenenden (CRLF→LF), BOM und doppelt kodiertes UTF-8
  repariert (verhinderte den Container-Start je nach Editor/OS des Autors).

### Security
- Fail-Fast beim Start, wenn `SECRET_KEY` in Produktion fehlt oder ein
  bekannter unsicherer Platzhalter ist (statt einer scheinbar normal
  laufenden, aber kompromittierbaren App).

## [0.5.0] - 2026-07-12

### Added
- Kompakte Listenansicht (optional), Filter/Sortierung für Gegenstände-,
  Verbrauchsmaterial- und Mitarbeiter-Listen.
- Detailseiten für Gegenstände/Verbrauchsmaterial.
- Größere Thumbnails, Bild-Vorschau per Lightbox.

### Fixed
- Mobile Listenansicht: sich überlappender Karteninhalt.
- Fehlender Warenkorb-Button bei Verbrauchsmaterial in der Listenansicht;
  zu aggressive Titel-Kürzung.
- Service Worker lieferte nach Deploy veraltetes CSS aus.
- Mobiler Scroll-Bug; interner Status wird externen Nutzern nicht mehr
  angezeigt.
- 6 Funde aus einem Code-Review behoben.

## [0.4.0] - 2026-07-09 – 2026-07-11

### Added
- Migrationsskript Scandy2 (MongoDB) → Scandy-Lite (PostgreSQL) implementiert.
- Mobile-UI-Grundlage, Berechtigungsmodell (Rolle pro Abteilung).
- Warenkorb-Workflow für Reservierungen; PWA-Optimierungen; Top-Navigation.
- Service Worker + Offline-Hinweis.
- CSRF-Schutz für alle formularverarbeitenden Routen.

### Fixed
- Consumable-Bestand-Race-Condition (gleichzeitige Anpassungen konnten
  negativen Bestand erzeugen) durch atomares UPDATE mit Guard behoben.
- Redirect-Fehlermeldungen wurden nicht escaped.
- Scandy2-Import: migrierte Benutzer bekamen gar keine Abteilungsrolle.
- Kamera/Signatur-Aufnahme (zwei Fixrunden).
- Flaky Test-Setup: dateibasiertes statt In-Memory-SQLite für echte
  Nebenläufigkeit in Tests.

## [0.3.0] - 2026-07-04

### Added
- Phase 5: Historie-Ansicht.

### Changed
- Einstellungen-UI grundlegend überarbeitet (Tabs statt Scroll-Seite).

### Fixed
- Caddy-/TLS-Konfiguration, UI-Bilder, Dropdown-Darstellung, Rollen-Zuordnung.

## [0.2.0] - 2026-07-02 – 2026-07-03

### Added
- Phase 3: CRUD für Gegenstände/Verbrauchsmaterial/Mitarbeiter.
- Phase 4: Quickscan (Ausleihe/Rückgabe/Entnahme).

### Fixed
- Diverse Phase-4-Nachbesserungen.

## [0.1.0] - 2026-07-01

### Added
- Phase 1: Datenmodell + DB-Layer (FastAPI, SQLModel, PostgreSQL).
- Phase 2: Auth + Abteilungs-Scoping + Frontend-Fundament.
- Portainer-Deployment: Dockerfile + Produktions-Compose-Stack.

### Fixed
- Login-Redirect-Schleife über reines HTTP (Cookie-Secure-Flag griff
  fälschlich auch ohne TLS-Terminierung).
