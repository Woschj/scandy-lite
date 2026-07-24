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

## [0.18.4] - 2026-07-24

### Fixed
- **LXC-Installer: `sudo: command not found` beim PostgreSQL-Datenbank-Setup.**
  `setup_postgresql_db()` aus der geteilten Bibliothek nutzt intern
  `sudo -u postgres psql ...` - im offiziellen community-scripts-Ablauf
  bereits Teil des von `build_container()` installierten Basis-Pakets, das
  wir bewusst nicht nutzen (siehe Kommentar in `ct/scandy-lite.sh`). Die
  minimale Debian-12-Vorlage bringt `sudo` nicht mit. Jetzt explizit vor dem
  PostgreSQL-Setup mitinstalliert.

## [0.18.3] - 2026-07-24

### Changed
- **LXC-Installer: sichtbarer Fortschritt + etwas schneller.**
  `VERBOSE=yes` vor dem Laden von `misc/install.func` gesetzt - die geteilte
  Bibliothek leitet `apt`/`pip`/etc. sonst standardmäßig still in eine
  Logdatei um (`$STD`-Wrapper), ohne das offizielle Advanced-Settings-Menü
  gab es dafür keinen anderen Schalter. Grundpakete-Installation
  (`curl`/`git`) im Launcher zeigt bei endgültigem Fehlschlag jetzt die
  letzte tatsächliche Fehlermeldung statt nur "Netzwerk-Problem?". `pip
  install` installiert nur noch Laufzeit-Abhängigkeiten (Test-/Lint-Tools
  wie `pytest`/`ruff` werden aus der gemeinsamen `requirements.txt`
  herausgefiltert statt eine zweite Datei zu pflegen) und nutzt
  `--prefer-binary`, um versehentliche Kompilier-Versuche auszuschließen.

## [0.18.2] - 2026-07-24

### Changed
- **LXC-Installer: Disk-Default von 6 auf 16 GB erhöht** - bei
  Thin-Provisioning (Standard bei `local-lvm`) nur eine Obergrenze, kein
  reservierter Platz, kostet also nichts. Gibt Puffer für Datenbank +
  hochgeladene Item-/Consumable-Bilder, falls das Inventar deutlich wächst.
  Bei Bedarf jederzeit nachträglich erweiterbar per
  `pct resize <CTID> rootfs +10G`, auch ohne Thin-Provisioning.

## [0.18.1] - 2026-07-24

### Fixed
- **LXC-Installer: Storage-Auswahl schlug fehl** (`pct create` brach mit
  "storage 'local' does not support container directories" ab) - die
  Auswahlmenüs für "Storage (Rootfs)" und "Storage (Template)" teilten sich
  bisher eine ungefilterte `pvesm status`-Liste und konnten so `local`
  (unterstützt meist nur `vztmpl`/`iso`/`backup`, kein `rootdir`) als
  Rootfs-Storage vorschlagen. Beide Listen werden jetzt getrennt per
  `pvesm status --content rootdir` bzw. `--content vztmpl` gefiltert.
- **LXC-Installer: RAM-Default zu knapp** - 1024 MB/512 MB Swap reichten
  beim Testen nicht für `apt-get dist-upgrade` während der
  Container-Einrichtung (führte zu starkem Swapping und einer entsprechend
  sehr langsamen Installation ohne sichtbaren Fortschritt, da die Ausgabe
  dieses Schritts von der geteilten Helper-Bibliothek in eine Logdatei statt
  auf den Bildschirm umgeleitet wird). Neuer Default: 2048 MB RAM / 1024 MB
  Swap, weiterhin über "Erweitert" anpassbar.

## [0.18.0] - 2026-07-24

### Added
- **Nativer Proxmox-VE-LXC-Installer** (`proxmox/ct/scandy-lite.sh` +
  `proxmox/install/scandy-lite-install.sh`) - an die community-scripts-
  Konvention angelehnt (nutzt deren generische, app-unabhängige Helper aus
  `misc/install.func`/`misc/tools.func`: `setup_postgresql`,
  `create_self_signed_cert`, `msg_info`/`msg_ok`, ...), aber bewusst ohne
  deren `build.func`: dessen `build_container()` lädt das
  App-Installationsskript hart-codiert aus dem offiziellen
  community-scripts/ProxmoxVE-Repo, das würde für ein eigenständiges Skript
  wie dieses (kein offizieller community-scripts-Eintrag) ins Leere laufen.
  Stattdessen legt `ct/scandy-lite.sh` den Container direkt per
  `pct create` an und reicht die Installation per `pct exec` hinein.
  Installiert die App ohne Docker direkt in eine frische Debian-LXC:
  PostgreSQL, Python-venv, Repo-Klon nach `/opt/scandy-lite`,
  Alembic-Migrationen, Admin-Bootstrap, zwei systemd-Dienste (`scandy-lite`
  auf Port 8000 für HTTP, `scandy-lite-https` auf Port 8443 mit uvicorns
  eingebautem TLS über ein selbstsigniertes Zertifikat - ersetzt den
  separaten Caddy-Container aus dem Docker-Setup, der ausschließlich für
  dieses eine Zertifikat lief). Erneuter Aufruf des Skripts mit der
  Container-ID einer bestehenden Installation aktualisiert diese per
  `git fetch`/`git reset --hard` gegen `origin/master` (das Repo pflegt
  aktuell keine GitHub-Releases, daher direkt gegen den Branch statt
  release-basiert). `INSTALL.md` führt diesen Weg jetzt als primäre
  Installationsmethode,
  der bestehende Docker/Portainer-Weg bleibt als dokumentierte Alternative
  bestehen.

## [0.17.0] - 2026-07-22

### Changed
- **Separaten "Zugriff"-Tab aufgelöst** - Zugriffsrollen pro Abteilung
  (Nutzer/Mitarbeiter) werden jetzt direkt auf der Benutzer-Bearbeiten-Seite
  gesetzt, in einer Checkliste mit einer Rollen-Auswahl pro Abteilung, im
  selben Formular wie die restlichen Stammdaten. Grund: zwei getrennte
  Screens für "Heimat-Abteilung" und "Zugriffsrolle" waren die eigentliche
  Ursache des in 0.16.1 gefixten Bugs (Änderung an der einen Stelle wirkte
  an der anderen nicht) - mit nur noch einem Screen kann das strukturell
  nicht mehr auseinanderlaufen. Mehrere Abteilungen gleichzeitig bleiben
  möglich (z.B. Mitarbeiter in Werkstatt, gleichzeitig Nutzer in Büro).
  Die schnelle Ersteinrichtung beim Anlegen eines Benutzers (Heimat-
  Abteilung + eine Zugriffsrolle in einem Schritt) bleibt unverändert.
  Admin-Konten räumen beim Umschalten auf Admin ihre (dann wirkungslosen)
  Abteilungsrollen automatisch auf.
  Die Benutzer-Liste zeigt weiterhin auf einen Blick, wer wo welche Rolle
  hat (nur die Bearbeitung ist jetzt an einer Stelle). Vier neue/ersetzte
  Tests in `tests/test_user_edit.py`.

## [0.16.1] - 2026-07-22

### Fixed
- **Heimat-Abteilung eines Mitarbeiters ändern nahm die Zugriffsrolle nicht
  mit** (gemeldeter Bug: "ich konnte Mitarbeitern keine Abteilungen
  zuweisen" - Speichern wirkte erfolgreich, im Zugriff-Tab blieb die Person
  aber an der alten Abteilung hängen). Heimat-Abteilung (`User.department_id`,
  bestimmt den Ausweis) und Zugriffsrolle (`UserDepartmentRole`, bestimmt
  was die Person sehen/verwalten darf - siehe Tab "Zugriff") sind zwei
  getrennte Datensätze; `update_user` änderte bisher nur den ersten.
  Wechselt jetzt die Rolle mit auf die neue Heimat-Abteilung um (nur die
  Rolle AN DER ALTEN Heimat-Abteilung - zusätzliche Rollen in anderen
  Abteilungen bleiben unangetastet; existiert an der neuen Abteilung schon
  eine eigene Rolle, gewinnt die). Drei neue Regressionstests in
  `tests/test_user_edit.py`.

## [0.16.0] - 2026-07-22

### Fixed
- **Gegenstände/Verbrauchsmaterial ließen sich nach dem Anlegen NIE wieder
  einer anderen Abteilung zuordnen** (gemeldeter Bug: "nachträgliches
  Zuweisen/Ändern von Abteilungen wird nicht übernommen") - das Bearbeiten-
  Formular zeigte das Abteilungsfeld gar nicht erst an, `update_item`/
  `update_consumable` nahmen `department_id` serverseitig nicht mal als
  Parameter entgegen. Jetzt nachträglich änderbar:
  - Formular zeigt/erlaubt die Abteilungsauswahl auch beim Bearbeiten,
    Kategorie/Standort/Zusatzfelder reagieren reaktiv auf die gewählte
    Abteilung (gleiches Alpine-Muster wie beim Anlegen, jetzt für beide
    Modi vereinheitlicht) - ein bestehender, nicht mehr in den Vorgaben der
    aktuellen Abteilung auftauchender Kategorie-/Standort-Wert bleibt beim
    Laden erhalten statt beim nächsten Speichern stillschweigend zu leeren.
  - Blockiert, solange der Gegenstand noch ausgeliehen oder reserviert ist
    bzw. das Material noch vorgemerkt ist - Lending/Reservation/
    ConsumableReservation.department_id wird beim Anlegen immer vom Item/
    Material übernommen und mehrere Stellen (unter anderem der in 0.15.0
    N+1-optimierte `purge_department`) verlassen sich darauf, dass das
    dauerhaft stimmt.
  - Erfordert Mitarbeiter-Rolle in der ZIEL-Abteilung, nicht nur der
    aktuellen - sonst könnte sich jemand per Formular in eine Abteilung
    "hineinverschieben", in der er keine Rechte hat.
  - Neue Regressionstests (`tests/test_department_reassignment.py`) decken
    Erfolgsfall, beide Blockaden und die Berechtigungsprüfung ab.

## [0.15.0] - 2026-07-21

### Changed
- `python-jose` durch `PyJWT` ersetzt (Session-/Access-Token-Handling in
  app/core/security.py) - jose bekommt praktisch keine Updates mehr
  (letzter Release 2021), PyJWT ist aktiv gepflegt. Verhalten unverändert
  (gleiche `exp`-Prüfung, gleiche Fehlerbehandlung bei ungültigem Token).
- `purge_item`/`purge_consumable`/`purge_user` (app/core/trash.py) nutzen
  jetzt denselben `_close_open_or_block`-Helper wie `purge_department`
  (vorher dreifach dupliziertes "offene Ausleihe/Reservierung blockiert
  oder wird bei force automatisch geschlossen"-Muster).
- `purge_department` überspringt jetzt den redundanten Item-/Consumable-
  eigenen Offen-Check (`skip_open_check`): die department-weite Prüfung hat
  bereits ALLE Items/Material der Abteilung abgedeckt (department_id kommt
  beim Anlegen immer vom Item/Material, ist unveränderlich) - spart bei
  großen Abteilungen viele redundante Queries. `purge_user` bleibt bewusst
  ungekürzt (ein Mitarbeiter kann offene Ausleihen in einer ANDEREN
  Abteilung haben, die die department-weite Prüfung nicht sieht - siehe
  neuer Regressionstest `test_department_delete_blocked_by_member_open_lending_in_other_department`).
- Ruff als lokales Lint-Werkzeug eingerichtet (`ruff.toml`, `ruff check .`)
  - bewusst nicht Teil einer CI-Pipeline. Dabei gefundene echte Probleme
  behoben: verlorene Exception-Chains (`raise ... from None` bei bewusst
  in Kontrollfluss-Exceptions übersetzten `ValueError`n), mehrdeutiger
  Variablenname `l` (Verwechslungsgefahr mit `1`/`I`) an 8 Stellen, tote
  Imports.

## [0.14.0] - 2026-07-21

### Added
- Barcode-Aufkleber-Workflow beim Anlegen von Gegenständen/Verbrauchsmaterial:
  Kamera-Scan-Button direkt am Barcode-Feld (füllt nur das Feld, sendet das
  Formular NICHT automatisch ab wie beim Quickscan - Bezeichnung etc. fehlen
  ja noch). Scanner-Pistolen tippen den Code + Enter; Enter im Barcode-/
  Namensfeld springt jetzt zum nächsten Feld statt das halb ausgefüllte
  Formular abzuschicken (`data-scanner-enter="next"`, app/static/js/form-guard.js).
- Barcode-Generieren-Button beim Benutzer-Anlegen/-Bearbeiten (`MA-<Kürzel>`)
  - hier gibt es keinen Aufkleber zu scannen, der Ausweis wird von der App
  selbst gedruckt (siehe Mitarbeiterausweis-Feature).
- Tägliche Mindestbestand-Mail (app/core/low_stock.py): sammelt
  Verbrauchsmaterial auf/unter Mindestbestand und schickt eine Sammel-Mail an
  alle aktiven Admins mit hinterlegter E-Mail-Adresse - macht aus dem
  passiven roten Chip in der Liste eine aktive Benachrichtigung. Läuft als
  Hintergrund-Task ab dem Start (app/main.py::lifespan), kein externer Cron
  nötig.
- "+ Nachschub"-Stepper jetzt auch auf der Material-Detailseite (vorher nur
  in der Listenansicht) - wer über Scan/Suche direkt auf der Detailseite
  landet, muss nicht mehr erst zurück zur Liste.
- Backup/Restore-Anleitung in INSTALL.md (`pg_dump`/`psql`, Uploads-Volume) -
  bisher stand nirgends, wie man die Datenbank sichert.

### Fixed
- Bild-Verarbeitung (Pillow: Decode/EXIF-Rotation/Resize/Encode) und
  bcrypt-Passwort-Hashing/-Verifikation liefen synchron im Event-Loop -
  beides ist CPU-gebunden und blockierte für die Dauer JEDEN anderen
  gleichzeitigen Request auf demselben Worker (ein Bild-Upload oder Login
  bremste alle anderen Nutzer spürbar aus). Beides läuft jetzt über
  `run_in_threadpool`.
- `/static` (CSS/JS) und `/uploads` (Bilder) wurden ganz ohne
  `Cache-Control`-Header ausgeliefert - jede Anfrage brauchte einen
  Revalidierungs-Roundtrip zum Server. Versionierte Assets (`?v=<Version>`,
  seit 0.13.0 alle CSS/JS-Referenzen) werden jetzt ein Jahr lang
  unrevalidiert aus dem Browser-Cache bedient; Uploads (dieselbe URL kann
  sich durch Ersatz-Upload inhaltlich ändern) bekommen eine kurze,
  revalidierende Cache-Dauer statt gar keiner.

## [0.13.0] - 2026-07-21

### Added
- Zentrales Logging-Setup (`logging.basicConfig`, Level aus `ENV` abgeleitet) -
  bisherige `logger.info`/`debug`-Aufrufe liefen zuvor ohne Konfiguration
  ins Leere. `/health` prüft jetzt echt die Datenbank (`SELECT 1`), liefert
  `503` statt `200` bei Ausfall, damit der Docker-`HEALTHCHECK` einen
  DB-Ausfall tatsächlich erkennt.
- Globaler 500-Fehler-Handler (`app/templates/errors/500.html`): ein
  unerwarteter Fehler wird jetzt geloggt (mit Traceback) und zeigt eine
  ruhige Fehlerseite statt eines rohen Stacktrace oder eines nichtssagenden
  Server-Fehlers.
- Pagination für die Gegenstände-/Verbrauchsmaterial-Listen (analog zur
  Historie) - verhindert unbegrenztes Laden bei wachsendem Bestand.
- Fail-Fast beim Start, wenn `POSTGRES_PASSWORD` in Produktion noch der aus
  `docker-compose.yml` bekannte Platzhalter ist (gleiches Muster wie der
  bestehende `SECRET_KEY`-Check).
- Datenbank-Indizes für die in Listen gefilterten Spalten (`Item.status/
  category/location`, `Consumable.quantity/category/location`).

### Fixed
- Top-Navigation kollidierte auf Desktop-Breiten um 1280px (Logo klebte am
  ersten Menüpunkt, "Einstellungen" lief in den Benutzernamen, "Mein Ausweis"
  brach zweizeilig um): Mindestabstände + `nowrap`, volle Leiste erst ab
  1201px, darunter Hamburger-Menü (vorher schon ab 1025px volle Leiste, die
  dort nicht hineinpasste).
- Auf Mobilgeräten waren Übersicht, "Mein Ausweis" und Einstellungen
  überhaupt nicht erreichbar (nicht in der Bottom-Tab-Bar, Hamburger dort
  ausgeblendet) - der Hamburger ist jetzt auch mobil sichtbar.
- Einstellungen → Benutzer: die vierte Aktion ("Entfernen") wurde auf
  schmalen Screens am Kartenrand abgeschnitten und war nicht antippbar
  (`flex-shrink: 0` ohne `flex-wrap`); die "(du)"-Markierung des eigenen
  Kontos schwebte frei in der Aktionsspalte statt beim Namen zu stehen.
- Veralteter Hinweistext auf der Reservierungen-Seite beschrieb den
  Vor-Merge-Workflow ("Mitarbeiter bearbeiten → Login zuordnen") - jetzt
  der reale Weg (Einstellungen → Benutzer → Bearbeiten, Feld "Barcode").
- `scripts/seed_admin.py` legte den ersten Admin ohne `approved_at` an -
  seit dem SSO-Update tauchte ein so angelegter Admin fälschlich als
  "ausstehendes Konto" auf und hätte dort sogar abgelehnt (= gelöscht)
  werden können.
- Veraltetes CSS/JS nach Deploys: Browser durften Assets mangels
  Cache-Control-Header heuristisch wiederverwenden - auch durch den
  network-first Service Worker hindurch (dessen `fetch()` nutzt denselben
  HTTP-Cache). Alle CSS/JS-Einbindungen tragen jetzt eine versionierte URL
  (`?v=<App-Version>`), die sich mit jedem Release ändert.

### Changed
- Einstellungen-Navigation neu: auf breiten Screens vertikale Tab-Leiste
  links neben dem Inhalt (alle neun Bereiche dauerhaft sichtbar, sticky),
  auf schmalen Screens eine umbrechende Pill-Reihe - ersetzt die
  horizontale Scroll-Leiste mit Fade-Rand und Pfeil-Buttons, die immer
  einen Teil der Punkte versteckte.
- Der orange "Scannen"-CTA-Pill der Desktop-Navigation erschien im
  Hamburger-Dropdown als deplatzierter vollbreiter Balken - dort jetzt
  eine normale Listenzeile mit Akzent-Punkt und Fettschrift.
- Top-Nav-Beschriftungen: "Verbrauchsmaterial" → "Material" (deckungsgleich
  mit der Bottom-Tab-Bar), Emoji aus "Mein Ausweis" entfernt (einziges
  Emoji in einer sonst SVG-Icon-basierten Oberfläche, plattformabhängige
  Darstellung).
- Diverse Code-Smells aus einem Production-Readiness-Audit behoben:
  dreifach dupliziertes Mitarbeiter-Barcode-Lookup in `scan.py`
  zusammengefasst, inkonsistenter Enum-Vergleich in `reservations.py`
  vereinheitlicht, Mindestpasswortlänge als Konstante statt hartkodierter
  `8`, Rollen-Prüfungen in `admin_settings.py` über `UserRole`-Enum statt
  rohe Strings.
- Betrieblich relevante `IntegrityError`-Fälle (Race Conditions bei
  gleichzeitigem Anlegen/Ändern/Ausleihen) loggen jetzt eine Warnung mit
  Kontext, bevor die für Nutzer ohnehin unveränderte Fehlermeldung
  zurückgegeben wird.
- Sauberer Shutdown: `engine.dispose()` beim Herunterfahren.

## [0.12.0] - 2026-07-18

### Added
- Optionales SSO-Login via OpenID Connect (z.B. gegen einen selbst gehosteten
  Authentik-Server) - leer lassen (`OIDC_ISSUER`/`OIDC_CLIENT_ID`/
  `OIDC_CLIENT_SECRET`) schaltet das Feature komplett aus, die Login-Seite
  zeigt dann nur das lokale Formular. Erster Login einer bislang unbekannten
  Person legt automatisch ein Konto an, aber GESPERRT (`approved_at` NULL) -
  ein Admin muss es erst freischalten und dabei Abteilung + Rolle festlegen.
  Neue Seite "Ausstehende Konten" (`/admin/pending-accounts`) dafür, mit
  Hinweis-Banner auf der Übersicht, sobald Konten warten. Nutzt `Authlib`
  (neue Abhängigkeit) statt eigener Token-/JWKS-Verifikation.

## [0.11.0] - 2026-07-18

### Added
- Scannen des Mitarbeiter-Ausweis-Barcodes (statt Gegenstand/Verbrauchsmaterial)
  am Haupt-Scan-Screen leitet bei offener(n) Reservierung(en) jetzt direkt zur
  Sammel-Ausgabe weiter (`/scan/pickup/{worker_id}`), statt "nicht gefunden"
  zu melden - schließt den Kreis mit dem neuen Mitarbeiterausweis/QR-Code:
  Nutzer reserviert → Personal scannt den QR-Ausweis → Checkliste zum Abhaken
  → eine Unterschrift bestätigt die Ausgabe. Ohne offene Reservierung gibt es
  einen kurzen Hinweis statt der irreführenden "nicht gefunden"-Meldung.

## [0.10.0] - 2026-07-17

### Added
- Mitarbeiterausweis wieder eingeführt (`/me/ausweis` zur Selbstbedienung,
  `/admin/users/{id}/ausweis` für Admins): eigener Barcode als QR-Code, in
  einer Vollbild-Karte (kein Nav/Tabbar, "Ausweis drucken"-Button) - dieselbe
  Ansicht dient sowohl der Handy-Vorzeige-Nutzung als auch dem Ausdrucken
  (`@media print` blendet die Bedienelemente aus). QR statt klassischem
  Strichcode, weil sich lineare Barcodes von einem beleuchteten Handy-Display
  aus deutlich schlechter scannen lassen.

### Changed
- Einstellungen-Seite entschlackt: Tab-Leiste läuft jetzt in einer Zeile
  (horizontal scrollbar mit Fade-Rand + Pfeil-Buttons statt sichtbarer
  nativer Scrollbar), alle "Neu anlegen"-Formulare hinter einem "+ Neu"-
  Button eingeklappt statt dauerhaft sichtbar, Benutzer-Zeilen zweizeilig
  (Name/Login oben, Rollen-Chips klar abgesetzt darunter) statt einer
  überladenen Inline-Reihe, redundante "Aktiv"-Chips (Normalzustand) entfernt.

## [0.9.0] - 2026-07-17

### Changed
- Item/Consumable-CRUD-Duplizierung aufgelöst: `app/core/inventory_crud.py`
  bündelt Presets-Auflösung sowie Löschen/Bild-Upload/Bild-Löschen für beide
  Typen, Router sind jetzt dünne Wrapper. Gleiches Prinzip für die
  Papierkorb-Routen in `admin_settings.py` (jetzt inkl. Benutzer über
  dieselbe Konfiguration).
- `purge_department` (app/core/trash.py) entschlackt: der dreifach
  wiederholte Force/Block-Block für offene Ausleihen, Reservierungen und
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
- Abteilungen können kaskadierend gelöscht werden (Gegenstände, Material und
  Mitarbeiter werden mitgelöscht, Historie bleibt als Text-Schnappschuss
  erhalten); Force-Löschen schließt offene Ausleihen, Reservierungen und
  Material-Vormerkungen dabei automatisch ab, statt den Vorgang zu blockieren.

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
