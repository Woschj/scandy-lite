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
- [x] **Legacy-Migration Scandy2 (MongoDB) → Scandy-Lite (PostgreSQL)** + **Import direkt in der Weboberfläche** (dieser Stand)
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

### Weitere Fixes (dieser Stand)

- **Mitarbeiter-Login-Verknüpfung war nur beim Bearbeiten möglich, nicht beim
  Anlegen** - musste man einen neuen Mitarbeiter direkt mit einem Login
  verknüpfen wollen, ging das nur über den Umweg "erst anlegen, dann
  bearbeiten". Jetzt im selben Formular verfügbar wie beim Bearbeiten.
- **Bildschirm-Rotation:** Erster Versuch war ein blockierender "Bitte Gerät
  drehen"-Hinweis - auf Nutzer-Feedback hin durch echte Querformat-
  Unterstützung ersetzt (siehe nächster Abschnitt).

### Querformat-Unterstützung (statt Blockieren)

Ursprünglich gab es einen Overlay, der Handys im Querformat komplett
blockierte ("Bitte Gerät drehen") - stattdessen jetzt aktive Unterstützung,
da Querformat für manche (z.B. beim Kamera-Scannen) tatsächlich praktisch
sein kann:

- Eigene Media Query für Handy-Querformat (`orientation: landscape` +
  `max-height: 500px`, damit Tablets im Querformat unberührt bleiben):
  Top-Leiste und Tab-Bar werden schmaler (44px/52px statt 60px/72px), um
  im knappen Vertikalraum mehr Platz für den eigentlichen Inhalt zu lassen.
- Tab-Bar wechselt im Querformat von gestapeltem Icon-über-Text-Layout zu
  Icon-neben-Text (spart Höhe, ohne die Tap-Fläche zu verkleinern).
- Kamera-Vorschau orientiert sich im Querformat an der verfügbaren Höhe
  (`max-height`) statt stur `width: 100%` zu nutzen, damit sie nicht über
  den knappen Vertikalraum hinausschießt.
- PWA-Manifest wieder auf `"orientation": "any"` (keine erzwungene Sperre
  mehr).

**Tab-Bar generell (auch im Hochformat) komfortabler gemacht** - war laut
Rückmeldung "klein und fiddly zu bedienen": größere Icons (26px statt
22px), größere Schrift, mehr Höhe (72px statt 64px), plus sichtbares
Tap-Feedback (kurzes Aufhellen beim Antippen statt nur Farbwechsel des Texts).

### Fixes nach echtem Geräte-Test (iPhone-Screenshot)

Zwei konkrete, per Screenshot gemeldete Probleme behoben:

- **Top-Leiste lief über den rechten Rand hinaus** ("Abmelden" abgeschnitten):
  Abteilungs-Dropdown + Username + Abmelden waren zusammen zu breit für schmale
  Viewports, ohne dass irgendwas geschrumpft/versteckt wurde. Jetzt auf Mobilgeräten:
  Username-Text ausgeblendet (steht eh im Konto), Abteilungs-Select schmaler mit
  Ellipsis bei langen Namen, Abmelden bleibt immer erreichbar. Wichtig dabei: nicht
  einfach "das erste `<span>`" versteckt, sondern gezielt nur den Username - sonst
  wäre versehentlich auch die Abteilungs-Anzeige für Mitarbeiter ohne Umschalter
  mit verschwunden.
- **Kamera erforderte Scrollen:** Das Formular (Barcode-Feld, Suchen-Button)
  blieb bisher über der Kamera-Vorschau stehen, wenn die Kamera aktiv war - man
  musste erst herunterscrollen, um sie zu sehen. Jetzt blendet sich das Formular
  aus, sobald die Kamera startet (und wieder ein, wenn man sie schließt oder ein
  Scan erfolgreich war) - die Kamera erscheint direkt im sichtbaren Bereich.
  Zusätzlich scrollt die Seite automatisch sanft zur Kamera, als Sicherheitsnetz
  falls trotzdem noch Inhalt darüber steht. Betrifft alle drei Scan-Kontexte
  (Hauptscan, Ausgabe/Entnahme-Bestätigung, Sammel-Ausgabe).

Danke an dieser Stelle für den echten Screenshot vom Gerät - deutlich präziser
als jede Design-Durchsicht ohne echtes Gerät.

### Warenkorb + Sammel-Ausgabe (dieser Stand)

Ziel: beide Perspektiven (Nutzer reservieren, Personal gibt aus) sollen sich auf
einem Handy so nativ wie möglich anfühlen, nicht wie eine Web-Formular-Seite.

- **Fixierte Aktionsleiste am unteren Rand** (`.mobile-fixed-cta`): "Warenkorb
  absenden" bleibt auf dem Warenkorb immer in Daumen-Reichweite sichtbar, statt
  dass man bei vielen Einträgen erst nach unten scrollen muss - klassisches
  Native-App-Pattern (wie ein Kassenbon-Button in Einkaufs-Apps). Sitzt oberhalb
  der Tab-Bar, mit korrektem `safe-area-inset-bottom` für Geräte mit Notch/Home-Indicator.
- **"In den Warenkorb" ist jetzt ein echter, gefüllter Button** statt eines
  schmalen Textlinks - für Nutzer ist das die einzige/primäre Aktion auf der
  Karte und sollte entsprechend aussehen (48px Mindesthöhe, volle Kartenbreite).
- **Größeres, zentriertes Scan-Eingabefeld** (`.scan-input-large`, 56px hoch,
  1.25rem Schrift) einheitlich auf allen Scan-Seiten (Hauptscan, Ausgabe/Rückgabe,
  Sammel-Ausgabe) - wirkt mehr wie ein App-Eingabeelement als ein Formularfeld.
- **Haptisches Feedback** bei jedem Scan-Erfolg/-Fehler, auch in der neuen
  Sammel-Ausgabe (vorher nur auf der Hauptscan-Seite).
- **Sprung-Link "↓ Zur Bestätigung"** in der Sammel-Ausgabe, sobald mindestens
  ein Gegenstand abgehakt ist - erspart das manuelle Scrollen an einer
  potenziell langen Checkliste vorbei zur Unterschrift.

**Ehrlicher Hinweis:** Ich kann hier kein echtes Mobilgerät testen - alle
Anpassungen sind eine sorgfältige Design-Durchsicht nach etablierten Mobile-
Patterns (Daumen-Reichweite, Touch-Ziel-Größen, native Bestätigungs-Leisten),
aber kein Ersatz für einen echten Test auf einem Telefon. Bitte insbesondere
die fixierte Warenkorb-Leiste und das Scan-Eingabefeld einmal live ausprobieren.

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

### Bugfix: Kamera lud nicht ("kein Internetzugriff")

`@zxing/library` (die ursprüngliche Wahl) ist primär für Bundler gedacht - beim
Einbinden per einfachem `<script>`-Tag stand kein zuverlässiges globales
`ZXing`-Objekt zur Verfügung (kein `"browser"`-Feld im Paket, `"main"` zeigt
auf einen CommonJS-Build). Umgestellt auf **html5-qrcode**, eine Bibliothek,
die genau für Kamera-Scan per Script-Tag ohne Bundler gebaut und dafür
dokumentiert ist. API-technisch: statt eines fertigen `<video>`-Elements
erwartet sie ein leeres Container-`<div>`, in das sie ihr eigenes
Video-/Canvas-Element einhängt.

Auch mit der neuen Bibliothek dann die Meldung "kein Internetzugriff?" -
die URL selbst war korrekt (per npm-Registry verifiziert), aber euer internes
Netz erreicht `unpkg.com` offenbar generell nicht, genau wie schon einmal beim
Wall-Ink-Projekt. Alle drei externen JS-Bibliotheken (htmx, Alpine.js,
html5-qrcode) werden deshalb jetzt **selbst gehostet**
(`app/static/js/vendor/`) statt per CDN geladen - damit ist die App komplett
unabhängig von ausgehendem Internetzugriff des Browsers. Jede Datei wurde vor
dem Einbinden auf externe Laufzeit-Abhängigkeiten geprüft (keine gefunden -
alle drei sind in sich geschlossene Bundles).

Nicht mit umgestellt: Google Fonts (IBM Plex Mono/Sans) - rein kosmetisch,
fällt bei Nichterreichbarkeit automatisch auf System-Schriften zurück statt
etwas kaputtzumachen. Bei Bedarf lässt sich das nachträglich ebenfalls
selbst hosten (das Font-Paket ist allerdings deutlich unhandlicher, >180MB
Rohgröße für alle Schnitte).

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

Beim Anlegen kann direkt eine Zugriffsrolle (Nutzer/Mitarbeiter) für die
Heimat-Abteilung mitgegeben werden - sonst sieht der neue Login trotz
Abteilungsauswahl zunächst nichts (Heimat-Abteilung = nur der Ausweis, nicht
automatisch Zugriff). Weitere Abteilungen/Rollen danach im Tab "Zugriff".
Benutzer lassen sich außerdem nachträglich bearbeiten (Name, Passwort,
Admin-Status) - *Einstellungen → Benutzer → Bearbeiten*.

### Bugfix: Benutzer löschen schlug mit 500 fehl (Fremdschlüssel-Verletzung)

`update or delete on table "users" violates foreign key constraint
"fk_workers_user_id"` - der verknüpfte Mitarbeiter-Ausweis wurde beim Löschen
zwar als gelöscht markiert (Soft-Delete), behielt aber `user_id` weiterhin
gesetzt. Postgres verweigert dann zu Recht das Löschen des Logins, weil noch
ein Datensatz darauf zeigt - ein Soft-Delete ändert nichts an der Spalte
selbst. Fix: `user_id` wird jetzt explizit auf `None` gesetzt, nicht nur
`deleted_at`. In der eigenen Testumgebung nie aufgefallen, weil SQLite (dort
verwendet) Fremdschlüssel standardmäßig gar nicht prüft, anders als Postgres -
dieselbe Klasse Lücke wie beim Enum-Bug zuvor, jetzt mit `PRAGMA
foreign_keys=ON` in den eigenen Tests behoben.

## Löschen vs. Deaktivieren

Benutzer lassen sich jetzt **echt löschen** (*Einstellungen → Benutzer*), nicht nur
deaktivieren - unproblematisch, weil keine Ausleih-/Historien-Daten direkt an
einem User hängen (die referenzieren Worker, nicht User; eine Worker-Verknüpfung
wird beim Löschen sauber aufgelöst statt zu verwaisen).

Gegenstände, Verbrauchsmaterial und Mitarbeiter bleiben bewusst beim **Soft-Delete**
(nur "entfernt"-Markierung) - sie hängen an Ausleih-/Reservierungs-Historie, ein
echtes Löschen würde diese Historie zerreißen. Kategorien/Standorte sind unkritisch
und lassen sich echt löschen.

**Abteilungen** lassen sich jetzt ebenfalls echt löschen (*Einstellungen →
Abteilungen*) - aber nur, wenn sie wirklich **komplett leer** sind (keine
Gegenstände/Material/Mitarbeiter/Zugriffs-Zuweisungen/Kategorien/Standorte/
Ausleihen/Reservierungen, auch keine soft-gelöschten - die zählen als "war mal
was drin" mit). Ist noch was drin, zeigt die Fehlermeldung genau, was zuerst weg
muss. Zum Aufräumen von Karteileichen/Duplikaten (z.B. aus einem Test-Import)
reicht das in der Praxis meistens; für eine Abteilung mit echter Historie bleibt
weiterhin nur Deaktivieren.

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

## Historie: gruppierte Ausleihen + sichtbare Unterschrift

Zwei Probleme behoben, die die Historie faktisch unbrauchbar machten:

- **Unterschriften wurden zwar gespeichert, aber nirgendwo angezeigt** - jede
  Ausleihe/Ausgabe wird zwar mit digitaler Unterschrift bestätigt und landet
  auch in der Datenbank (`lendings.signature`, base64-PNG), aber es gab keine
  Stelle, die sie je wieder zeigt. Jetzt in der Historie pro Ausleih-Eintrag
  aufklappbar ("Unterschrift ansehen").
- **Jede Ausleihe/Rückgabe war ein eigener Zeitleisten-Eintrag** - eine
  Sammel-Ausgabe von 20 Gegenständen erschien als 20 (bzw. 40 mit Rückgabe)
  einzelne, unzusammenhängende Zeilen. Jetzt nach **Ausgabe-Vorgang**
  gruppiert: Gegenstände mit derselben Unterschrift (= derselbe
  Bestätigungsvorgang, egal ob Einzel- oder Sammel-Ausgabe) erscheinen als
  EIN aufklappbarer Eintrag ("20 Gegenstände — Person X"), mit Status-Chip
  ("ausgeliehen" / "N/M noch offen" / "alle zurückgegeben") und beim
  Aufklappen dem Einzelstatus jedes Gegenstands.

Gruppierungsschlüssel ist bewusst (Mitarbeiter, Unterschrift) - eine
Unterschrift gehört immer zu genau einem Bestätigungsvorgang, ganz ohne
eigene "Sitzung"/"Vorgang"-Tabelle. Aus Scandy2 importierte Alt-Ausleihen
ohne Unterschrift bleiben einzeln (eine Gruppierung über eine gemeinsame
"keine Unterschrift" würde alle Alt-Ausleihen einer Person fälschlich in
einen Topf werfen).

## Reservierungs-Workflow

1. **Reservieren/Vormerken (Warenkorb):** Eingeloggte Nutzer mit verknüpftem Mitarbeiter-Ausweis
   (Verknüpfung: Mitarbeiter → Bearbeiten → Login zuordnen, oder direkt beim Anlegen über
   das "Zugriffsrolle"-Feld) sehen sowohl bei Gegenständen als auch bei Verbrauchsmaterial
   einen **"In den Warenkorb"**-Button (bei Verbrauchsmaterial mit Mengen-Stepper). Der
   Warenkorb ist rein clientseitig (localStorage, `app/static/js/cart.js`) - Einträge
   sammeln, seitenübergreifend (auch nach Abteilungswechsel), ohne dass beim Hinzufügen
   ein Seitenwechsel oder Server-Roundtrip passiert. Erst unter *Reservierungen → 🛒 Warenkorb
   öffnen* wird der Inhalt geprüft (Verfügbarkeit/Bestand kann sich zwischenzeitlich geändert
   haben) und gesammelt abgeschickt - dort verwalten Nutzer auch ihre bestätigten
   Reservierungen/Vormerkungen (inkl. Storno).

   Gegenstände werden dabei **exklusiv** reserviert (ein Exemplar, ein Vorgang). Verbrauchsmaterial
   wird **weich** vorgemerkt - mehrere Personen können denselben Bestand gleichzeitig anfragen
   (kein harter Lagerbestand-Held), es wird nur gewarnt, wenn die Summe aller offenen
   Vormerkungen den aktuellen Bestand übersteigt. Personal entscheidet beim Scannen nach
   eigenem Ermessen.

   **Bestände sind für die Rolle Nutzer nicht sichtbar** - nur "Verfügbar"/"Nicht verfügbar",
   keine genaue Zahl (auch nicht im HTML-Quelltext, z.B. über das Mengen-Eingabefeld). Mitarbeiter
   und Admin sehen weiterhin die exakten Bestandszahlen, die für die Lagerverwaltung nötig sind.
2. **Sammel-Ausgabe (mehrere Gegenstände auf einmal):** Unter *Scannen → 📋 Reservierungen
   ausgeben* wählt Personal eine Person mit offenen Reservierungen aus und sieht eine
   Checkliste aller vorgemerkten Gegenstände. Barcode für Barcode abscannen (auch per Kamera) -
   jeder Treffer wird sofort abgehakt. Fehlt ein Gegenstand, lässt er sich direkt aus der
   Abholung **entfernen** (storniert nur diese eine Reservierung, der Rest läuft normal weiter).
   Am Ende **eine** Unterschrift für alle abgehakten Gegenstände zusammen - erst dann werden
   die Ausleihen tatsächlich angelegt. Der "was ist schon abgescannt"-Zwischenstand lebt
   bewusst nur in der URL zwischen den Schritten, keine eigene Datenbank-Tabelle nötig.
3. **Einzel-Ausgabe/Entnahme:** Der normale Scan-Workflow funktioniert weiterhin für einzelne
   Gegenstände/Vorgänge. Bei Gegenständen: ist er reserviert, wird der Mitarbeiter-Barcode
   vorausgefüllt und die Ausgabe an andere Personen blockiert; die Ausgabe wird mit
   **digitaler Unterschrift** (Canvas, Finger/Maus) bestätigt — serverseitig Pflicht. Bei
   Verbrauchsmaterial: normale Entnahme über `/scan/consume`, offene Vormerkungen werden dort
   als Kontext angezeigt, aber nicht hart erzwungen.
4. **Rückgabe (nur Gegenstände):** Gegenstand einfach erneut scannen → Rückgabe mit einem Klick.

**Admin-Übersicht (dieser Stand):** Unter *Reservierungen → Alle offenen Reservierungen* sind
Einträge **nach Person gruppiert** statt einzeln aufgelistet - reserviert jemand 20 Gegenstände,
erscheint das als EINE aufklappbare Zeile ("Person X — 20 Gegenstände"), nicht als 20 einzelne
Karten. Aufklappen (natives `<details>`, kein JS nötig) zeigt die Einzelposten mit
Stornier-Möglichkeit pro Eintrag, plus einen direkten Link zur Sammel-Ausgabe für genau diese
Person.

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

Zwei Wege, je nach Bedarf:

- **In der Weboberfläche** (*Einstellungen → 📥 Import aus Scandy2*): Scandy2-Backup-ZIP
  hochladen (Scandy2: *Einstellungen → Backup → "Backup erstellen"*), Vorschau ansehen,
  bestätigen. Kein Kommandozeilen-/Datenbankzugriff nötig - der empfohlene Weg für den
  normalen Umstieg.
- **Kommandozeilenskript** (`migrations_legacy/migrate_from_mongodb.py`): für Fälle, in
  denen direkter MongoDB-Zugriff einfacher ist als ein Backup zu erstellen (z.B. sehr
  große Bestände, oder wenn man selektiv nur einzelne Collections migrieren will).
  Details in [`migrations_legacy/README.md`](migrations_legacy/README.md).

**Wichtige Einschränkung des Weboberflächen-Wegs:** Scandy2s eigenes Backup exportiert die
`users`-Collection aus Sicherheitsgründen nie (weder beim mongodump- noch beim JSON-Fallback-
Pfad - eine bewusste Entscheidung im Scandy2-Code selbst). Über den Import kommen deshalb
immer Gegenstände/Material/Mitarbeiter-Ausweise/Historie, aber nie Benutzer-Logins mit -
die müssen danach separat unter *Einstellungen → Benutzer* angelegt und den importierten
Mitarbeiter-Ausweisen zugeordnet werden (*Mitarbeiter → Bearbeiten → Verknüpfter Login*).
Das Kommandozeilenskript hat diese Einschränkung nicht (liest direkt aus der Datenbank,
wo `users` natürlich vorhanden ist).

Beide Wege sind idempotent (mehrfach ausführbar ohne Duplikate) und starten standardmäßig
als Trockenlauf, der nur einen Report zeigt, bevor wirklich geschrieben wird.
