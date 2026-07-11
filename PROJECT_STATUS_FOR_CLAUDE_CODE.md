# Scandy-Lite — Projektstatus-Übergabe für Claude Code

> Dieses Dokument fasst Scope, Zielsetzung, Architektur und den aktuellen
> Umsetzungsstand zusammen, damit eine neue Claude-Code-Sitzung ohne den
> gesamten bisherigen Chatverlauf produktiv weiterarbeiten kann. Das
> ausführlichere, laufend gepflegte `README.md` im Repo-Root bleibt die
> primäre Referenz für Details — dieses Dokument ist die kuratierte
> Kurzfassung mit Fokus auf "was ist der Zustand, was sind die Fallstricke".

## 1. Was ist das, und warum gibt es das

**Scandy-Lite** ist eine schlanke Ausleihe-/Ausgabe-Verwaltung für Werkzeuge
und Verbrauchsmaterial mit Mehr-Abteilungs-Unterstützung. Es ist eine
**saubere Neuentwicklung** (nicht Fortentwicklung) von **Scandy2**
(altes System, Flask + MongoDB, Repo: `MD-BTZ/btz-scandy`), reduziert auf den
Kern-Workflow: kein Ticketsystem, kein Kantinenplan, keine Job-Verwaltung.

**Auftraggeber-Kontext:** Andreas arbeitet bei der Rheinischen Hochschule
Köln (RH Köln) in einer IT-nahen Rolle. Scandy-Lite soll Scandy2 als
Inventar-/Ausleihsystem für mehrere Abteilungen (Werkstatt, Büro, IT, ...)
ablösen. Deployment erfolgt über Portainer (Docker-Compose-Stacks) auf einem
Proxmox-Server. Interner Netzwerkbetrieb ohne generellen Internetzugriff nach
außen war mehrfach relevant (siehe Abschnitt 6, "selbst gehostete
JS-Bibliotheken").

## 2. Tech-Stack

- **Backend:** FastAPI (async), SQLModel, Alembic-Migrationen
- **Datenbank:** PostgreSQL (Produktion), SQLite (nur für Tests/Sandbox —
  **PRAGMA foreign_keys muss explizit aktiviert werden**, sonst verdeckt
  SQLite reale FK-Bugs, die gegen Postgres krachen — siehe Abschnitt 7)
- **Frontend:** Server-rendertes Jinja2 + HTMX + Alpine.js (Tabs in den
  Einstellungen), eigenes Design-System (IBM Plex Mono/Sans, "Werkstatt-
  Inventaranhänger"-Optik)
- **Mobile:** PWA (installierbar), Kamera-Barcode-Scan via **html5-qrcode**
  (selbst gehostet, nicht CDN — siehe Abschnitt 6)
- **Auth:** lokal (bcrypt-Hashes), Modell ist LDAP/SSO-vorbereitet
  (`auth_source`, `external_id`, `hashed_password` nullable), aber nicht
  angebunden
- **Deployment:** Docker Compose, Portainer-Stack (Repository-Methode),
  optionaler `caddy`-Service für HTTPS (Kamera-Scan braucht sicheren
  Kontext — HTTP funktioniert nur auf `localhost`, nicht auf einer LAN-IP)

## 3. Architektur / Datenmodell

Alle Tabellennamen sind Plural, Modell-Klassen Singular (SQLModel-Konvention).
**Wichtig: die Kern-Entität heißt `Item`/`items`, nicht `Tool`/`tools`** (bewusste
Namensentscheidung — "Gegenstand" ist neutraler als "Werkzeug", nicht jede
Abteilung leiht zwangsläufig Werkzeuge aus).

| Tabelle | Zweck |
|---|---|
| `departments` | Abteilungen — zentrale Mandantentrennung |
| `users` | System-Logins, LDAP/SSO-vorbereitet |
| `user_department_roles` | Rolle (Mitarbeiter/Nutzer) pro User UND Abteilung — siehe Abschnitt 4 |
| `workers` | Personen, die ausleihen (Barcode-Ausweis), optional mit `user_id` verknüpft |
| `items` | Gegenstände (ex-"tools") |
| `consumables` | Verbrauchsmaterial mit Bestand |
| `lendings` | Ausleihen (`returned_at IS NULL` = aktuell ausgeliehen), inkl. `signature`-Feld (base64-PNG) |
| `consumable_usages` | Entnahme-/Nachschub-Protokoll |
| `reservations` | Gegenstand-Reservierungen (exklusiv, ein Exemplar) |
| `consumable_reservations` | Verbrauchsmaterial-Vormerkungen (weich, mit Menge, mehrere Personen gleichzeitig möglich) |
| `categories` / `locations` | Presets pro Abteilung (Autocomplete, kein Zwang) |

**Zentrales Architekturprinzip überall:** "eine Quelle der Wahrheit" statt
Status-Feld-Sync. Ob ein Gegenstand ausgeliehen ist, ergibt sich aus
`lending.returned_at IS NULL`, nicht aus einem separaten `status`-Feld, das
man vergessen könnte zu synchronisieren. Gleiches Prinzip bei Reservierungen
(`fulfilled_at`/`cancelled_at` beide NULL = offen).

### Berechtigungsmodell (überarbeitet, aktueller Stand)

Kein Gruppen-Konzept mehr. Stattdessen:
- **Admin** = globales Flag auf `User.is_admin`, voller Zugriff überall,
  kein Abteilungs-Eintrag nötig.
- Alle anderen bekommen ihre Rolle **direkt pro Abteilung** zugewiesen
  (`UserDepartmentRole`, verwaltet unter *Einstellungen → Zugriff*) — eine
  Person kann in mehreren Abteilungen unterschiedliche Rollen haben
  (z.B. Mitarbeiter in Werkstatt UND Nutzer in Büro gleichzeitig).
- **Mitarbeiter**-Rolle (pro Abteilung): verwalten (anlegen/bearbeiten/
  löschen), scannen (Ausgabe/Rückgabe/Entnahme), Historie einsehen.
- **Nutzer**-Rolle (pro Abteilung): nur ansehen + reservieren/vormerken.
- **Der Abteilungs-Switcher wurde komplett entfernt** (siehe Abschnitt 5) —
  Nutzer sehen automatisch nur, wozu sie eine Rolle haben; Admins sehen
  immer alles gleichzeitig, Abteilung ist beim Anlegen/Bearbeiten einfach
  ein normales Formularfeld.

### "Jeder Benutzer ist auch Mitarbeiter"

Jeder neue Login bekommt beim Anlegen automatisch einen verknüpften
Mitarbeiter-Ausweis (eigener Barcode) — kein manuelles Verknüpfen mehr nötig
für den Normalfall. Ausnahme: der Bootstrap-Admin (`scripts/seed_admin.py`)
bekommt keinen automatischen Ausweis (Skript fragt keine Namens-/
Barcode-Daten ab). Manuelles Verknüpfen bleibt als Fallback (*Mitarbeiter →
Bearbeiten → Verknüpfter Login*), funktioniert jetzt auch schon beim
**Anlegen** eines neuen Mitarbeiters (war ein gemeldeter Bug — nur beim
Bearbeiten möglich, jetzt behoben).

Löschen/Deaktivieren eines Logins wirkt sich auf den verknüpften Ausweis aus
(deaktivieren → Ausweis deaktiviert; löschen → Ausweis soft-gelöscht,
`user_id` explizit auf NULL gesetzt — siehe FK-Bug in Abschnitt 7).

## 4. Kern-Workflows (aktueller Stand, alle implementiert + E2E-getestet)

### Reservieren (Nutzer-Perspektive) — Warenkorb

- Gegenstände UND Verbrauchsmaterial haben einen "In den Warenkorb"-Button.
- Warenkorb ist **rein clientseitig** (localStorage, `app/static/js/cart.js`)
  — kein Server-Roundtrip beim Hinzufügen, bleibt über Seiten-/
  Abteilungswechsel hinweg erhalten.
- Gegenstände: exklusiv reserviert (ein Exemplar, ein Vorgang, DB-Unique-Index
  gegen Race-Conditions).
- Verbrauchsmaterial: **weich** vorgemerkt (Menge), kein harter Bestands-Held
  — mehrere Personen können denselben Bestand gleichzeitig anfragen, nur eine
  Prüfung "Summe aller offenen Vormerkungen ≤ aktueller Bestand".
- **Bestände sind für die Rolle Nutzer nicht sichtbar** (nur "Verfügbar"/
  "Nicht verfügbar", auch nicht im HTML-Quelltext über z.B. ein `max`-Attribut
  am Mengenfeld). Mitarbeiter/Admin sehen weiterhin exakte Zahlen.
- Warenkorb-Seite (`/reservations/cart`) prüft beim Öffnen die aktuelle
  Verfügbarkeit (fetch gegen `/reservations/cart/items`) und sendet erst auf
  Bestätigung gesammelt ab (`/reservations/cart/submit`).

### Ausgeben (Personal-Perspektive) — Einzeln + Sammel-Ausgabe

- **Einzeln:** normaler Scan-Workflow (`/scan`) — Barcode scannen, bei
  Reservierung wird der Mitarbeiter-Barcode vorausgefüllt, Ausgabe mit
  **digitaler Unterschrift** (Canvas) bestätigt, serverseitig Pflichtfeld.
- **Sammel-Ausgabe** (`/scan/pickup`, neueres Feature): Personal wählt eine
  Person mit offenen Reservierungen, sieht eine Checkliste, scannt
  Gegenstände nacheinander ab (auch per Kamera) — jeder Treffer wird
  abgehakt. Fehlende Gegenstände lassen sich direkt aus der Abholung
  **entfernen** (storniert nur diese eine Reservierung, Rest läuft weiter).
  **Eine** Unterschrift am Ende für alle abgehakten Gegenstände zusammen.
  Der "was ist schon abgescannt"-Zwischenstand lebt bewusst nur als
  Query-Parameter zwischen den Schritten (kein Session-Tabellen-Overhead).

### Reservierungs-Übersicht (Admin) — gruppiert

Unter *Reservierungen → Alle offenen Reservierungen*: Einträge sind **nach
Person gruppiert** (natives `<details>`, kein JS) statt einzeln aufgelistet
— reserviert jemand 20 Gegenstände, ist das EINE aufklappbare Zeile, nicht
20 Karten. Direkter Link zur Sammel-Ausgabe für genau diese Person.

### Historie — gruppiert + Unterschrift sichtbar

Unter `/history`: gemeinsame chronologische Zeitleiste (Ausleihen +
Verbrauchsmaterial-Entnahmen). Zwei wichtige, kürzlich behobene Probleme:
- Unterschriften wurden zwar gespeichert, aber nirgendwo angezeigt — jetzt
  pro Ausleih-Eintrag über "Unterschrift ansehen" aufklappbar (`<img
  src="data:image/png;base64,...">` direkt aus der DB-Spalte).
- Ausleihen werden nach **(Mitarbeiter, Unterschrift)** gruppiert — eine
  Unterschrift gehört immer zu genau einem Bestätigungsvorgang, egal ob
  Einzel- oder Sammel-Ausgabe. Legacy-Ausleihen ohne Unterschrift (aus dem
  Scandy2-Import) bleiben bewusst einzeln, um nicht fälschlich alle
  Alt-Ausleihen einer Person zusammenzuwerfen.

## 5. Mobile-UX (intensiv iteriert, mit echtem Geräte-Feedback)

Der Nutzer hat mehrfach **echte iPhone-Screenshots** geschickt — das war
jedes Mal deutlich präziser als reine Design-Vermutungen. Wichtige Learnings:

- **Abteilungs-Switcher komplett entfernt** (nicht nur versteckt) — auch für
  Admins. Grund: mit dem Rollenmodell aus Abschnitt 3 ist "aktuell aktive
  Abteilung als Seiten-Kontext" überflüssig geworden; Abteilung ist beim
  Anlegen/Bearbeiten einfach ein normales Auswahlfeld.
- **Top-Nav lief auf schmalen Viewports über den rechten Rand** ("Abmelden"
  abgeschnitten) — behoben durch gezieltes Ausblenden/Verkleinern einzelner
  Elemente (Username-Text weg, Abteilungs-Chip mit Ellipsis), NICHT durch
  pauschales Verstecken des ersten `<span>` (hätte versehentlich auch die
  Abteilungs-Anzeige für Mitarbeiter ohne Mehrfachrolle getroffen).
- **Kamera-Vorschau erforderte Scrollen** — Formular/Überschrift blieben
  über der Kamera stehen. Fix: `barcode-camera.js` hat einen
  `hideWhileActive`-Parameter — blendet ein übergebenes Element beim
  Kamera-Start komplett aus (auf der Hauptscan-Seite: die GESAMTE
  Seiten-Chrome, nicht nur das Formular) und zentriert die Kamera-Karte
  vertikal (`body.camera-active`-CSS-Klasse).
- **Querformat wurde erst geblockt, dann aktiv unterstützt** (Kurskorrektur
  auf Nutzer-Feedback: Querformat ist beim Scannen praktisch). Eigene
  Media-Query-Anpassungen für Handy-Querformat (schmalere Nav/Tab-Bar,
  Tab-Bar-Layout wechselt zu Icon-neben-Text).
  **Wichtiger Bug dabei:** Die primäre "bin ich im Mobil-Modus"-Erkennung
  hing NUR an `max-width: 720px` — ein Handy im Querformat ist aber
  *breiter* als das (z.B. ~850px bei einem iPhone), fiel komplett auf die
  Desktop-Navigation zurück ("wie eine Desktop-App, die krampfhaft auf einen
  Handyscreen soll", O-Ton Nutzer). Fix: alle mobilen Media-Queries prüfen
  jetzt zusätzlich `(max-height: 500px) and (orientation: landscape)`,
  unabhängig von der Breite.
- **Tab-Bar war "klein und fiddly"** — vergrößert (26px Icons, mehr Höhe,
  sichtbares Tap-Feedback beim Antippen).
- Touch-Targets durchgängig auf 44px Mindesthöhe, Mengen-Stepper statt
  Zahlenfelder, haptisches Feedback (`navigator.vibrate`) bei Scan-Erfolg/
  -Fehler, Doppel-Submit-Schutz (`form-guard.js`, `data-guard`-Attribut).

**Ehrlich zu kommunizieren, falls die nächste Session weiter daran arbeitet:**
Es gibt in dieser Sandbox **kein echtes Mobilgerät zum Testen** — alle
CSS/Layout-Anpassungen sind sorgfältige Durchsicht nach etablierten
Patterns, aber Screenshots vom echten Gerät sind der einzige Weg, das
wirklich zu verifizieren. Bitte aktiv danach fragen bzw. den Nutzer bitten,
nach jeder größeren Mobile-Änderung nochmal zu testen.

## 6. Externe Abhängigkeiten — bewusst selbst gehostet

**Kein CDN-Zugriff verlassen** — das interne Netz beim Nutzer (RH Köln)
erreicht `unpkg.com` & Co. teils nicht (gleiches Muster wie bei einem
früheren Projekt des Nutzers, "Wall-Ink"). Alle drei JS-Bibliotheken
(htmx, Alpine.js, html5-qrcode) liegen deshalb unter
`app/static/js/vendor/` und werden vom eigenen Server ausgeliefert, nicht
per CDN geladen. Jede Datei wurde vor dem Einbinden auf fehlende externe
Laufzeit-Nachladungen geprüft.

**Nicht selbst gehostet:** Google Fonts (IBM Plex) — rein kosmetisch, fällt
bei Nichterreichbarkeit automatisch auf System-Schriften zurück, das
Font-Paket ist zudem mit >180MB deutlich unhandlicher.

`@zxing/library` (ursprüngliche Kamera-Bibliothek) wurde durch
**html5-qrcode** ersetzt — Zxing ist primär für Bundler gebaut, kein
zuverlässiges globales Objekt bei einfacher Script-Tag-Einbindung.
html5-qrcode ist genau für diesen Zweck dokumentiert/gebaut.

## 7. Wichtige Bugs & strukturelle Learnings (für künftige Arbeit relevant)

Diese Learnings sollten in künftigen Sessions **präventiv** angewendet
werden, nicht erst wenn der Bug auftritt:

1. **SQLite verdeckt reale Postgres-Bugs.** Standardtests liefen gegen
   SQLite, das (a) keine echten Enum-Typen kennt und (b) Fremdschlüssel
   standardmäßig NICHT prüft. Zwei reale Bugs (Enum-Typ doppelt angelegt,
   FK-Verletzung beim User-Löschen) fielen dadurch in eigenen Tests nie auf,
   krachten aber gegen echtes Postgres beim Nutzer. **Seit diesem Learning:
   Tests laufen mit `PRAGMA foreign_keys=ON`**, und Alembic-Migrationen mit
   nativen Enum-Typen brauchen `create_type=False`, wenn ein Typ in einer
   SPÄTEREN Migration wiederverwendet wird (nicht bei der Migration, die ihn
   ursprünglich erzeugt).
2. **Alembic `transaction_per_migration=True`** ist gesetzt (in
   `alembic/env.py`) — sonst laufen bei einem frischen Deployment ALLE
   ausstehenden Migrationen in EINER Transaktion, was bei
   `ALTER TYPE ... ADD VALUE` gefolgt von sofortiger Nutzung des neuen Werts
   in dieser Session zu "unsafe use of new value" führt (Postgres-Regel:
   neue Enum-Werte erst nach COMMIT nutzbar).
3. **Jinja + `dict.items()`-Kollision:** ein Gruppen-Dict mit Schlüssel
   `"items"` wird in `{{ g.items }}` als die eingebaute `dict.items()`-Methode
   aufgelöst, nicht als Dict-Zugriff. Schlüssel wie `items`/`keys`/`values`/
   `get` in dict-basierten Template-Kontexten vermeiden.
4. **`.dockerignore` muss mit App-Feature-Umfang mitwachsen:**
   `migrations_legacy/` war dort ausgeschlossen (korrekt, solange es nur ein
   Host-CLI-Skript war) — brach, als der Web-Import
   (`app/routers/admin_import.py`) diesen Code zur LAUFZEIT im Container
   brauchte. Bei neuen Features, die bestehende Verzeichnisse zur Laufzeit
   einbinden, `.dockerignore` gegenprüfen.
5. **CSS `!important` schlägt Inline-Styles**, aber nur wenn es selbst
   `!important` ist — wichtig bei Mobile-Overrides gegen vorhandene
   Inline-`style=`-Attribute in Templates.
6. **Defer-Skripte vs. Inline-Skripte:** ein `<script defer>` läuft immer
   NACH allen synchronen Inline-Skripten im Dokument, unabhängig von der
   Position im HTML. Ein Inline-Skript, das eine in einem deferred Skript
   definierte globale Funktion aufruft, muss selbst in `DOMContentLoaded`
   eingepackt werden.
7. **Event-Phasen bei mehreren `submit`-Listenern auf demselben Formular:**
   ein Capture-Phase-Listener (z.B. Doppel-Submit-Schutz) feuert VOR einem
   Bubble-Phase- oder direkt-am-Element-Listener (z.B. Signature-Validierung)
   — wenn Letzterer die Übermittlung abbricht, war der Erstere schon
   "fertig" und blockiert dauerhaft. Lösung: Bubble-Phase +
   `e.defaultPrevented`-Prüfung.

## 8. Legacy-Migration von Scandy2

Zwei Wege, beide idempotent, beide starten als Trockenlauf:

1. **Weboberfläche** (*Einstellungen → 📥 Import aus Scandy2*): Scandy2-
   Backup-ZIP hochladen, Vorschau, bestätigen. **Wichtige Einschränkung:**
   Scandy2-Backups enthalten NIE die `users`-Collection (bewusste
   Sicherheitsentscheidung im Scandy2-Code selbst, verifiziert) — Logins
   müssen nach dem Import manuell angelegt und mit importierten
   Mitarbeiter-Ausweisen verknüpft werden.
2. **CLI-Skript** (`migrations_legacy/migrate_from_mongodb.py`): direkter
   MongoDB-Zugriff, bringt auch User mit. Details in
   `migrations_legacy/README.md`.

Migrationslogik (`migrate_core.py`) ist zwischen beiden Wegen geteilt — die
Web-Variante läuft die synchrone Migrationsfunktion über
`asyncio.to_thread`, um den Event-Loop nicht zu blockieren.

## 9. Was noch offen ist / nicht umgesetzt

- **Phase 6 (README-Nomenklatur):** Service Worker für echten Offline-Betrieb
  fehlt noch (PWA-Manifest + Icons sind vorhanden, Installierbarkeit
  funktioniert, aber kein Offline-Shell-Caching).
- **Kein CSRF-Token** auf Formularen (bewusst zurückgestellt — SameSite=Lax
  Cookies fangen die gängigsten Angriffe ab, für ein internes Tool ohne
  Internet-Exposition als Restrisiko akzeptiert, aber nicht ideal).
- **LDAP/SSO** ist im Datenmodell vorbereitet, aber nicht angebunden.
- Mobile-Kamera-Zentrierung (`hideWhileActive`) ist bisher nur auf der
  Haupt-Scan-Seite umgesetzt, nicht auf `scan/result.html` (Ausgabe-
  Bestätigung) oder `pickup/checklist.html` (Sammel-Ausgabe) — dort blieb
  bewusst mehr Kontext sichtbar (Gegenstand-Infos, Checkliste), könnte bei
  Bedarf aber dieselbe Behandlung bekommen, falls dort auch Scroll-Probleme
  gemeldet werden.
- Google Fonts sind noch nicht selbst gehostet (siehe Abschnitt 6) — rein
  kosmetisches Restrisiko, kein Blocker.
- Kein echtes Mobilgerät zum Testen in dieser Sandbox verfügbar — alle
  Mobile-Iterationen liefen über vom Nutzer zugeschickte Screenshots.

## 10. Praktisch relevante Dateien/Pfade

```
app/
  main.py                    # Router-Registrierung
  core/
    config.py                # Settings (Pydantic), DATABASE_URL etc.
    database.py              # Async Engine/Session
    deps.py                  # get_current_user, require_admin, require_staff, populate_nav_context
    access.py                # get_visible_department_ids, is_staff_in_department
    security.py              # Passwort-Hashing (bcrypt)
    scandy2_import.py        # Parser für Scandy2-Backup-Format
  models/                    # Ein Modell pro Datei, siehe Abschnitt 3
  routers/
    items.py, consumables.py, workers.py    # CRUD
    scan.py                  # Quickscan (Ausleihe/Rückgabe/Entnahme)
    pickup.py                # Sammel-Ausgabe
    reservations.py          # Warenkorb + Reservierungen
    history.py                # Gruppierte Zeitleiste
    admin_settings.py         # Abteilungen/Benutzer/Zugriff/Presets
    admin_import.py           # Web-basierter Scandy2-Import
  static/
    css/app.css               # Komplettes Design-System, ein File
    js/
      cart.js, barcode-camera.js, signature.js, form-guard.js, qty-stepper.js
      vendor/                 # Selbst gehostete htmx/alpine/html5-qrcode
  templates/                  # Jinja2, Struktur folgt Router-Namen
alembic/versions/              # 10 Migrationen bisher
migrations_legacy/              # CLI-Migrationsskript + eigene Tests, eigenes requirements.txt
scripts/seed_admin.py            # Bootstrap-Admin für lokale Entwicklung
docker-compose.yml               # Produktiv-Stack (App + Postgres + optional Caddy)
docker-compose.dev.yml           # Nur Postgres, für lokale Entwicklung mit uvicorn --reload
INSTALL.md                       # Schritt-für-Schritt Portainer-Anleitung
```

## 11. Test-/Arbeitsweise, die sich bewährt hat

Für jede Änderung in dieser Session wurde konsequent so vorgegangen (bitte
fortführen):
1. Relevanten Code/Template erst ansehen, nicht aus dem Gedächtnis raten.
2. Änderung machen.
3. **Echten E2E-Test schreiben** (FastAPI `TestClient` gegen eine frische
   SQLite-DB mit `PRAGMA foreign_keys=ON`, `scripts.seed_admin.seed()` zum
   Bootstrap), der den tatsächlichen HTTP-Roundtrip prüft — nicht nur, dass
   der Code syntaktisch lädt.
4. Bei JS-Änderungen: `node --check` für Syntax, ggf. `jsdom` für echtes
   DOM-Verhalten (wurde z.B. beim Event-Phasen-Bug genutzt, um das ALTE
   fehlerhafte Verhalten nachzustellen und zu bestätigen, dass es sich
   wirklich um den gemeldeten Bug handelte).
5. README.md an der passenden Stelle aktualisieren (nicht nur anhängen —
   das Dokument ist mittlerweile lang, aber thematisch strukturiert).
6. Committen mit ausführlicher Commit-Message (Ursache, Fix, Verifikation).
7. Archiv packen (`tar`, ohne `.venv`/`.git`/`__pycache__`/DB-Dateien) und
   dem Nutzer zum Einspielen in sein lokales Repo geben (dieser Sandbox-
   Checkout ist nicht das Repo des Nutzers — es gibt keinen gemeinsamen
   Git-Remote, Änderungen müssen per Archiv transportiert werden).

**Deployment-Zyklus beim Nutzer:** lokaler Ordner leeren (außer `.git`),
Archiv entpacken, `git add/commit/push`, dann in Portainer bzw. lokal
`docker compose up -d --build`. Bei reinen Code-/Template-Änderungen ohne
neue Abhängigkeiten reicht `docker compose up -d` ohne `--build`.
