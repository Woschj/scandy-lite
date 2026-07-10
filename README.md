# Scandy-Lite

Schlanke Ausleihe/Ausgabe-Verwaltung für Werkzeuge und Verbrauchsmaterial,
mit Mehr-Abteilungs-Unterstützung. Extrahiert und clean neu aufgebaut aus
[scandy2](https://github.com/woschj/scandy2), reduziert auf den Kern-Workflow
(kein Ticketsystem, kein Kantinenplan, keine Job-Verwaltung).

**→ Schritt-für-Schritt-Installation via Portainer: [INSTALL.md](INSTALL.md)**

## Tech-Stack

- **Backend:** FastAPI (async)
- **Datenbank:** PostgreSQL + SQLModel + Alembic-Migrationen
- **Frontend:** HTMX + Alpine.js, eigenes Design-System (Grundlage steht, Item-Listen folgen Phase 3+)
- **Mobile:** PWA (installierbar, responsive), Kamera-Barcode-Scan folgt Phase 4
- **Auth:** lokal (Phase 1), LDAP/SSO andockbar ohne Schema-Umbau (siehe unten)

## Projektstatus

- [x] **Phase 1 — Datenmodell + DB-Layer**
- [x] **Phase 2 — Auth + Abteilungs-Scoping + Frontend-Fundament**
- [x] **Phase 3 — CRUD für Gegenstände/Verbrauchsmaterial/Mitarbeiter**
- [x] **Phase 4 — Quickscan: Ausleihe/Rückgabe/Entnahme**
- [x] **Phase 5 — Historie-Ansicht**
- [x] **Reservierungs-Workflow (Kanban)** — Reservieren per App → Ausgabe per Scan + digitale Unterschrift → Rückgabe per Scan
- [x] **Bild-Upload für Gegenstände/Verbrauchsmaterial** + **Einstellungen als Tabs statt Scroll-Seite**
- [x] **Rollenmodell: Admin (global) + Rolle pro Abteilung (Mitarbeiter/Nutzer)** (überarbeitet, dieser Stand)
- [x] **Legacy-Migration Scandy2 (MongoDB) → Scandy-Lite (PostgreSQL)**
- [x] **Ausleih-Workflow + Mobile-UX-Feinschliff**
- [ ] Phase 6 — Feinschliff UI/PWA (Offline-Hinweis, Service Worker, Einstellungsseiten-Layout)

## Berechtigungsmodell: Rolle pro Benutzer UND Abteilung

Das ursprüngliche Gruppen-Konzept ("Nutzergruppe hat Zugriff auf Abteilungen")
wurde durch ein direkteres Modell ersetzt, weil es einen unnötigen Umweg
darstellte: **Admin** ist ein globales Flag (voller Zugriff überall). Alle
anderen bekommen ihre Rolle **direkt pro Abteilung** zugewiesen
(*Einstellungen → Zugriff*) - eine Person kann in mehreren Abteilungen
unterschiedliche Rollen haben, z.B. Mitarbeiter in Werkstatt UND gleichzeitig
Nutzer in Büro.

Das löst den ursprünglichen Anwendungsfall (Studierende leihen Geräte aus
einer ANDEREN Abteilung, als der sie organisatorisch angehören) direkt, ohne
Umweg über eine Gruppen-Verwaltung: Der Person einfach "Nutzer"-Rolle in der
Abteilung geben, aus der sie ausleihen soll - fertig.

- **Sichtbarkeit** (Gegenstände/Material ansehen): jede Rolle (Mitarbeiter
  UND Nutzer) gewährt Sichtbarkeit in ihrer jeweiligen Abteilung
- **Verwaltung** (Anlegen/Bearbeiten/Löschen/Scannen/Ausgeben): nur die
  Mitarbeiter-Rolle, und zwar SPEZIFISCH für die betroffene Abteilung -
  Mitarbeiter-Rolle in Werkstatt erlaubt kein Bearbeiten in Büro
- Der Abteilungs-Switcher erscheint für JEDEN, der in mehr als einer
  Abteilung eine Rolle hat (vorher nur für Admins)

Migration: bestehende `role`+`department_id`-Kombination pro User wird
automatisch in genau einen entsprechenden Zugriffs-Eintrag übersetzt - beim
Deploy geht nichts verloren.


## Mobile-UX-Verbesserungen (Scan-Workflow)

- **Kamera-Scan jetzt auch für den Mitarbeiter-/Ausweis-Barcode** (nicht nur für
  den Gegenstand am Anfang) - direkt in den Ausgabe-/Entnahme-Formularen.
  Gemeinsames JS-Modul (`barcode-camera.js`), unterstützt mehrere Scan-Buttons
  pro Seite.
- **Haptisches Feedback** (Vibration) bei erfolgreichem Kamera-Scan und bei
  Erfolg/Fehler nach einer Aktion (`navigator.vibrate`, wo vom Gerät unterstützt).
- **Doppel-Submit-Schutz** (`data-guard`-Attribut, `form-guard.js`): Formulare mit
  Seiteneffekten (Ausleihe, Rückgabe, Entnahme, Reservieren, Anlegen/Bearbeiten)
  deaktivieren ihren Button nach dem ersten Tap - verhindert versehentliche
  Doppel-Buchungen bei langsamem Mobilfunknetz.
- **Mengen-Stepper** (–/+-Buttons, `qty-stepper.js`) statt Zahlenfeld-Tippen bei
  Verbrauchsmaterial-Entnahme und -Nachschub.
- **Touch-Targets vergrößert**: Karten-Aktionen (Bearbeiten/Entfernen/Reservieren)
  waren mit 32px unter der empfohlenen 44px-Mindestgröße für Touch-Bedienung -
  jetzt überall konsistent 44px.

Nicht mit einem echten Gerät testbar in dieser Umgebung (kein Browser mit
Kamera/Touch verfügbar) - bitte insbesondere den Kamera-Scan für den
Mitarbeiter-Barcode und die Stepper-Buttons einmal live ausprobieren.

### Bugfix: Kamera lud nicht

`@zxing/library` ist primär für Bundler gedacht - beim Einbinden per einfachem
`<script>`-Tag (unser Anwendungsfall) stand kein zuverlässiges globales
`ZXing`-Objekt zur Verfügung (das Paket hat kein `"browser"`-Feld, `"main"`
zeigt auf einen CommonJS-Build). Umgestellt auf **html5-qrcode** - eine
Bibliothek, die genau für Kamera-Scan per Script-Tag ohne Bundler gebaut und
offiziell dafür dokumentiert ist. API-technisch: statt eines fertigen
`<video>`-Elements erwartet sie ein leeres Container-`<div>`, in das sie ihr
eigenes Video-/Canvas-Element einhängt.

### Bugfix: Button blieb nach Unterschrift auf "Wird verarbeitet" hängen

Der Doppel-Submit-Schutz (`form-guard.js`) lief in der Capture-Phase - er
deaktivierte den Button, BEVOR der Unterschrift-Handler (`signature.js`, der
bei fehlender Unterschrift die Übermittlung per `preventDefault()` abbricht)
überhaupt zum Zug kam. Bricht dieser die Übermittlung ab, blieb der Button
dauerhaft deaktiviert, weil `form-guard.js` seine Sperre schon vorher gesetzt
hatte. Fix: Bubble-Phase (läuft NACH Handlern direkt am Formular) +
`e.defaultPrevented`-Prüfung, sodass nur wirklich abgesendete Formulare den
Button sperren. Per echter DOM-Simulation (jsdom) verifiziert, inkl. Nachbau
des alten (fehlerhaften) Verhaltens zur Bestätigung. Zusätzlich als
Sicherheitsnetz: automatische Freigabe nach 15s, falls aus einem anderen
Grund keine Weiterleitung erfolgt.

## Umstieg von Scandy2

Ein eigenständiges Migrationsskript übernimmt Bestandsdaten (Gegenstände,
Verbrauchsmaterial, Mitarbeiter, Ausleih-Historie, Benutzer) aus der alten
MongoDB-Instanz. Details, Nutzung und wichtige Hinweise (Passwörter können
nicht 1:1 übernommen werden!) in [`migrations_legacy/README.md`](migrations_legacy/README.md).


## Benutzer = Mitarbeiter

Jeder Login bekommt beim Anlegen automatisch einen verknüpften Mitarbeiter-Ausweis
(Barcode) - kein manuelles Verknüpfen mehr nötig. Wer sich einloggen kann, kann
sich damit auch selbst etwas ausleihen/reservieren (passend zur Rolle, die er in
der jeweiligen Abteilung hat).

Ausnahme: der allererste Admin-Account (`scripts/seed_admin.py`, Bootstrap beim
Deployment) bekommt keinen automatischen Ausweis, da das Skript keine
Namens-/Barcode-Angaben abfragt. Bei Bedarf lässt sich das nachträglich manuell
nachholen (*Mitarbeiter → Neu anlegen*, dann *Bearbeiten → Verknüpfter Login*)
- diese manuelle Verknüpfung bleibt als Fallback erhalten, für genau solche
  Altfälle und für Mitarbeiter-Datensätze, die schon vor einem Login bestanden.

Deaktivieren/Löschen eines Logins wirkt sich auf den verknüpften Ausweis aus:
deaktivieren deaktiviert auch den Ausweis, löschen löscht ihn mit (Soft-Delete -
die Ausleih-Historie bleibt erhalten, der Barcode wird wieder frei).

## Löschen vs. Deaktivieren

Benutzer lassen sich jetzt **echt löschen** (*Einstellungen → Benutzer*), nicht nur
deaktivieren - unproblematisch, weil keine Ausleih-/Historien-Daten direkt an
einem User hängen (die referenzieren Worker, nicht User; eine Worker-Verknüpfung
wird beim Löschen sauber aufgelöst statt zu verwaisen).

Gegenstände, Verbrauchsmaterial und Mitarbeiter bleiben bewusst beim **Soft-Delete**
(nur "entfernt"-Markierung) - sie hängen an Ausleih-/Reservierungs-Historie, ein
echtes Löschen würde diese Historie zerreißen. Kategorien/Standorte/Abteilungen/
Gruppen sind hingegen unkritisch und lassen sich echt löschen.

## Rollenmodell

| Rolle | Darf (jeweils PRO Abteilung, außer Admin) |
|---|---|
| **Admin** | Alles, überall: Einstellungen, Abteilungen wechseln, Benutzer verwalten, plus alles von Mitarbeiter — global, kein Abteilungs-Eintrag nötig |
| **Mitarbeiter** (in Abteilung X) | Gegenstände/Material/Mitarbeiter in X verwalten (anlegen/bearbeiten/löschen), Scannen (Ausgabe/Rückgabe/Entnahme), Historie einsehen |
| **Nutzer** (in Abteilung X) | Gegenstände/Material in X **ansehen**, Gegenstände **reservieren** (erfordert einen mit dem Login verknüpften Mitarbeiter-Datensatz), eigene Reservierungen einsehen/stornieren — keine Verwaltung, kein Scannen, keine Historie |

Eine Person kann in mehreren Abteilungen unterschiedliche Rollen haben (siehe
"Berechtigungsmodell" oben). Zugewiesen wird das unter *Einstellungen → Zugriff*.
Für Reservierungen zusätzlich nötig: den Login bei einem Mitarbeiter-Datensatz
verknüpfen (*Mitarbeiter → Bearbeiten → Verknüpfter Login*).

## Bild-Upload

Gegenstände und Verbrauchsmaterial können im Bearbeiten-Formular ein Foto bekommen
(JPEG/PNG/WebP, wird serverseitig validiert, EXIF-Rotation korrigiert, auf max.
900px verkleinert und einheitlich als JPEG gespeichert). Erscheint als Thumbnail
in der Liste und im Scan-Ergebnis. Liegt auf einem eigenen, persistenten
Docker-Volume (`scandy_lite_uploads`) — überlebt Rebuilds/Redeploys, anders als
der restliche Anwendungscode.

## Einstellungen

`/admin/settings` ist jetzt eine Tab-Ansicht (Abteilungen/Benutzer/Kategorien/
Standorte) statt einer langen Scroll-Seite — nur ein Bereich sichtbar,
Tab-Wechsel ohne Neuladen (Alpine.js). Die aktuell aktive Abteilung ist immer
sichtbar und wird beim Anlegen neuer Kategorien/Standorte automatisch vorausgewählt.

## Reservierungs-Workflow

1. **Reservieren:** Eingeloggte Nutzer mit verknüpftem Mitarbeiter-Ausweis (Verknüpfung: Mitarbeiter → Bearbeiten → Login zuordnen) sehen in der Gegenstands-Liste einen **Reservieren**-Button. Unter *Reservierungen* verwalten sie ihre Vormerkungen (inkl. Storno).
2. **Ausgabe:** An der Ausgabe wird der Gegenstand gescannt. Ist er reserviert, wird der Mitarbeiter-Barcode vorausgefüllt und die Ausgabe an andere Personen blockiert. Die Ausgabe wird mit **digitaler Unterschrift** (Canvas, Finger/Maus) bestätigt — serverseitig Pflicht.
3. **Rückgabe:** Gegenstand einfach erneut scannen → Rückgabe mit einem Klick.

Die **Übersicht** ist ein Kanban-Board: Spalten *Reserviert* → *Ausgeliehen* zeigen alle laufenden Vorgänge (mit ✓-Kennzeichnung unterschriebener Ausgaben). Benutzer-Logins werden unter *Einstellungen → Benutzer* angelegt (nur Admin).
  - [x] Kamera-basiertes Scannen (via optionalem Caddy-HTTPS-Proxy)
- [x] **Phase 7 — Docker-Setup für Produktivbetrieb** (vorgezogen für Portainer-Deployment)

## Historie

Unter `/history`: eine gemeinsame, chronologische Zeitleiste aus Ausleihen,
Rückgaben und Verbrauchsmaterial-Entnahmen (statt getrennter Historie-Seiten pro
Gegenstand/Mitarbeiter wie im Original - für ein schlankes System reicht eine
durchsuchbare Liste). Suche nach Gegenstand-/Material-/Mitarbeitername,
einfache Seitenweise-Navigation.

## Admin-Einstellungen

Unter `/admin/settings` (nur Admin-Rolle): Abteilungen anlegen/deaktivieren,
Kategorien- und Standort-Vorschläge pro Abteilung pflegen (Datalist-Autocomplete
in den Gegenstand-/Verbrauchsmaterial-Formularen - freies Textfeld bleibt weiterhin
möglich, die Presets sind nur Vorschläge, kein Zwang).

## Review-Durchgang (nach Phase 4)

Sicherheits-/Konsistenz-Check über alle bisherigen Phasen, gefundene und behobene Probleme:

- **Zeitzonen-Bug (kritisch für Produktivbetrieb):** Modelle nutzten `datetime.utcnow()`
  (naiv), neuere Router-Codes `datetime.now(timezone.utc)` (aware) - beide schrieben in
  dieselben `TIMESTAMP WITHOUT TIME ZONE`-Spalten. Auf SQLite fiel das nicht auf, gegen
  echtes Postgres/asyncpg hätte das beim Schreiben eines aware-Datetimes einen Fehler
  geworfen. Vereinheitlicht auf eine zentrale `utcnow()`-Funktion (naiv, ohne deprecated
  `datetime.utcnow()`-Aufruf).
- **Race-Condition beim Ausleihen:** zwei nahezu gleichzeitige Scans desselben Gegenstands
  konnten beide eine Lending anlegen. Jetzt durch einen Partial-Unique-Index
  (`uq_lendings_open_item`, nur eine offene Lending pro Gegenstand) auf DB-Ebene
  ausgeschlossen, Anwendung fängt den resultierenden Konflikt sauber ab statt mit 500er.
- **Unvalidierte UUID:** `worker_id` bei der Bestandsanpassung wurde ungeprüft geparst -
  hätte bei manipulierten Formulardaten zu einem 500er statt einer sauberen Fehlermeldung geführt.
- **Datenintegrität der künftigen Historie:** die Schnellanpassung in der
  Verbrauchsmaterial-Liste erlaubte negative Werte ganz ohne Mitarbeiter-Zuordnung -
  Entnahmen wären an der Historie vorbeigelaufen. Jetzt nur noch Nachschub (positiv) in
  der Liste, Entnahmen mit Zuordnung laufen bewusst nur noch über Quickscan.
- **Login-Rate-Limit** ergänzt (einfaches In-Memory-Limit, 10 Fehlversuche/5 Min. pro IP) -
  vorher kein Schutz gegen Brute-Force.
- **SECRET_KEY-Warnung:** Log-Warnung beim Start, falls in Produktion noch der
  Default-Wert gesetzt ist.

**Bekannte, bewusst nicht behobene Lücke:** kein CSRF-Token auf den Formularen. Die
Session-Cookies sind `SameSite=Lax`, was die gängigsten CSRF-Angriffe (cross-site POST)
bereits abfängt - für ein internes Tool ohne Internet-Exposition ist das Restrisiko
gering, aber nicht null. Vollständiger CSRF-Schutz (Token in jedem der ~20 Formulare)
wäre ein separater, größerer Umbau und ist aktuell zurückgestellt.

## Quickscan

Unter `/scan` (auch prominent in der Navigation/Tab-Bar): Barcode eintippen oder
mit einem angeschlossenen Scanner scannen (Scanner senden i.d.R. Enter nach dem
Scan, das reicht zum Absenden des Formulars - kein JS nötig). Je nach Fund:
- **Gegenstand verfügbar** → Mitarbeiter-Barcode angeben → Ausleihe wird erfasst
- **Gegenstand ausgeliehen** → Rückgabe mit einem Klick
- **Verbrauchsmaterial** → Menge + Mitarbeiter-Barcode → Bestand wird reduziert, Entnahme protokolliert
- **Unbekannter Barcode** → direkter Link zum Neuanlegen mit vorausgefülltem Barcode

Kamera-basiertes Scannen (statt externem Hardware-Scanner) ist ab diesem Stand
implementiert - siehe Hinweis zu HTTPS unten, ohne das funktioniert es nicht.

## Kamera-Scan & HTTPS

Browser verweigern Kamerazugriff (`getUserMedia`) grundsätzlich über reines
HTTP - Ausnahme ist nur `localhost`. Läuft die App wie bei euch über eine
LAN-IP per HTTP, ist der "📷 Mit Kamera scannen"-Button auf `/scan` zwar
sichtbar, zeigt aber automatisch einen Hinweis statt eines kaputten Buttons
("benötigt HTTPS") - der externe Hardware-Scanner/manuelle Eingabe funktioniert
davon unbenommen weiter.

**Um Kamera-Scan nutzbar zu machen**, liegt dem Compose-Stack ein optionaler
`caddy`-Service bei - ein Reverse-Proxy, der automatisch ein selbstsigniertes
Zertifikat erzeugt (kein Domain-/Let's-Encrypt-Aufwand nötig):

1. Stack wie gewohnt deployen (der `caddy`-Service startet automatisch mit)
2. Statt `http://<ip>:8010` aufrufen: `https://<ip>:8443`
3. Browser zeigt eine Zertifikatswarnung (unbekannte, selbstsignierte CA) -
   einmalig pro Gerät "Erweitert -> Trotzdem fortfahren" bestätigen
4. Danach funktioniert die Seite normal, inklusive Kamera-Zugriff

Der bisherige HTTP-Zugriff über `APP_PORT` bleibt parallel nutzbar - falls ihr
den `caddy`-Service nicht braucht, könnt ihr ihn und den `caddy_data`-Eintrag
einfach aus der `docker-compose.yml` entfernen. `SESSION_COOKIE_SECURE` muss
dafür **nicht** auf `true` gesetzt werden - nicht-sichere Cookies funktionieren
über HTTP und HTTPS gleichermaßen, nur umgekehrt (sicheres Cookie über HTTP)
wäre das Problem, das wir schon hatten.

## Begriff "Gegenstand" statt "Werkzeug"

Bewusst neutral gehalten (Modell `Item`, Tabelle `items`) statt "Tool"/"Werkzeug" -
nicht jede Abteilung leiht zwangsläufig Werkzeuge im engeren Sinn aus.

## Design-System

Signatur-Element: Karten im Look physischer Werkstatt-Inventaranhänger (Asset-Tags)
mit Perforationskante und Barcode-Streifen — zieht sich durch Login, Dashboard und
später durch alle Item-Karten. Typografie: **IBM Plex Mono** (Labels, Status, Barcodes)
+ **IBM Plex Sans** (Fließtext). Responsive: Top-Nav am Desktop, Bottom-Tab-Bar mobil
(Daumen-erreichbar, `env(safe-area-inset-bottom)`-sicher). PWA-Manifest + Icons bereits
vorhanden, Installierbarkeit kommt final in Phase 6 (Service Worker für Offline-Shell).

## Erster Login

- **Portainer:** über `ADMIN_USERNAME`/`ADMIN_PASSWORD` beim ersten Deploy (siehe unten)
- **Lokal:** über `scripts/seed_admin.py` (siehe unten)

Danach unter `/auth/login` anmelden.

## Datenmodell (Phase 1)

| Tabelle | Zweck |
|---|---|
| `departments` | Abteilungen — zentrale Mandantentrennung |
| `users` | System-Logins (Admin/Mitarbeiter), vorbereitet für LDAP/SSO |
| `workers` | Personen, die ausleihen (per Barcode-Ausweis, nicht zwingend ein System-Login) |
| `tools` | Werkzeuge |
| `consumables` | Verbrauchsmaterial mit Bestand |
| `lendings` | Werkzeug-Ausleihen (`returned_at IS NULL` = aktuell ausgeliehen) |
| `consumable_usages` | Entnahme-Protokoll für Verbrauchsmaterial |

### LDAP/SSO-Vorbereitung

Das `User`-Modell hat schon jetzt:
- `auth_source` (`local` / `ldap` / `sso`)
- `hashed_password` **nullable** (LDAP/SSO-User haben keins)
- `external_id` für die LDAP-DN oder SSO-Subject-ID

Wenn LDAP/SSO angebunden wird, kommt nur ein neuer Auth-Provider hinzu, der
`User`-Datensätze mit `auth_source="ldap"`/`"sso"` erzeugt/synchronisiert — der
Rest der App (Rechte, Abteilungs-Scoping, Ausleihe) bleibt unverändert.

## ⛴️ Installation via Portainer

Scandy-Lite ist als Portainer-Stack deploybar (App + PostgreSQL, ein Stack, kein separates DB-Setup nötig).

### Methode 1: Repository (empfohlen)

1. Repo zuerst auf GitHub pushen (siehe unten), dann in Portainer: **Stacks → Add stack**
2. **Build method:** Repository
3. **Repository URL:** dein Git-Remote, z. B. `https://github.com/woschj/scandy-lite.git`
4. **Compose path:** `docker-compose.yml`
5. **Environment variables:** siehe Tabelle unten
6. **Deploy the stack**

Portainer baut das Image dabei selbst aus dem `Dockerfile` im Repo (kein separates Image-Pushen nötig).

### Methode 2: Web Editor

1. **Stacks → Add stack → Web editor**
2. Inhalt von `docker-compose.yml` einfügen
3. Environment variables ergänzen (Tabelle unten)
4. **Deploy the stack**

Bei dieser Methode muss das Repo zusätzlich als „Additional files“/Build-Kontext verfügbar sein,
oder du baust das Image vorher selbst und trägst es im `image:`-Feld ein statt `build:`.
Für den Einstieg ist **Methode 1** deutlich unkomplizierter.

### ⚙️ Umgebungsvariablen

| Variable | Beschreibung | Default |
| :--- | :--- | :--- |
| `APP_PORT` | Port, unter dem die App per HTTP erreichbar ist | `8000` |
| `APP_HTTPS_PORT` | Port für den optionalen Caddy-HTTPS-Zugriff (Kamera-Scan) | `8443` |
| `POSTGRES_USER` | Datenbank-User | `scandy` |
| `POSTGRES_PASSWORD` | Datenbank-Passwort (**ändern!**) | `change_me_immediately` |
| `POSTGRES_DB` | Datenbankname | `scandy_lite` |
| `SECRET_KEY` | Signierschlüssel für Login-Sessions (**ändern!**) | `change_me_secret_key` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Session-Gültigkeit in Minuten | `720` (12h) |
| `SESSION_COOKIE_SECURE` | `true`, wenn ein Reverse-Proxy TLS terminiert. Bei reinem HTTP im internen Netz auf `false` lassen, sonst verwirft der Browser das Login-Cookie stillschweigend | `false` |
| `ADMIN_USERNAME` | Erster Admin-Login, wird beim Start automatisch angelegt | *(leer = kein Auto-Bootstrap)* |
| `ADMIN_PASSWORD` | Passwort dazu | *(leer)* |
| `DEFAULT_DEPARTMENT_CODE` | Kurzcode der ersten Abteilung | `werkstatt` |
| `DEFAULT_DEPARTMENT_NAME` | Anzeigename der ersten Abteilung | `Werkstatt` |

**Empfehlung:** `ADMIN_USERNAME`/`ADMIN_PASSWORD` nur beim ersten Deploy setzen, danach in
Portainer wieder leeren (Stack neu deployen) - das Skript überschreibt zwar nie ein
bestehendes Passwort, aber ein Klartext-Admin-Passwort muss nicht dauerhaft in der
Stack-Konfiguration stehen.

### 📁 Persistenz

- `scandy_lite_db_data` - PostgreSQL-Datenverzeichnis (Docker-Volume, überlebt Redeploys)

### Migrationen bei Updates

Der Container wendet beim Start automatisch `alembic upgrade head` an (siehe
`docker/entrypoint.sh`) - ein Redeploy nach einem `git pull` reicht, kein manueller
Migrations-Schritt nötig.

## 🛠️ Lokale Entwicklung

```bash
# 1. Nur Postgres lokal starten (App läuft direkt via uvicorn, für schnelles Reload)
docker compose -f docker-compose.dev.yml up -d

# 2. Virtualenv + Dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. .env anlegen
cp .env.example .env

# 4. Migrationen anwenden
alembic upgrade head

# 5. Ersten Admin-User anlegen
python -m scripts.seed_admin --username admin --password <sicheres-passwort>

# 6. App starten
uvicorn app.main:app --reload
```

Health-Check: `GET /health`

## Migrationen

```bash
# Neue Migration nach Modell-Änderungen generieren
alembic revision --autogenerate -m "kurze beschreibung"

# Anwenden
alembic upgrade head

# Zurückrollen
alembic downgrade -1
```

## Legacy-Datenmigration (Scandy2 → Scandy-Lite)

Nicht priorisiert, siehe [`migrations_legacy/README.md`](migrations_legacy/README.md)
für den geplanten Ansatz, sobald das relevant wird.
