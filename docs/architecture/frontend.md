# Frontend-Architektur

## Stack

Serverseitig gerenderte Jinja2-Templates (`app/templates/`), kein SPA-
Framework, kein Build-Step/Bundler. HTMX für punktuelle dynamische
Interaktionen, Alpine.js für kleinere clientseitige Zustände (z. B. Tabs in
den Einstellungen). Beide sowie `html5-qrcode` (Kamera-Barcode-Scan) liegen
selbst gehostet unter `app/static/js/vendor/` statt per CDN geladen -
interne Netze ohne generellen Internetzugriff nach außen sind der
Normalfall für dieses Tool (siehe `docs/security/secrets.md` zum
Deployment-Kontext), nicht die Ausnahme. Vor dem Einbinden jeder Vendor-
Datei prüfen, ob sie zur Laufzeit selbst wieder etwas nachlädt (CDN,
Analytics, Fonts) - genau das würde den Punkt zunichtemachen.

## Eigene JS-Module

Kleine, fokussierte Vanilla-JS-Dateien unter `app/static/js/`, je ein
Verhalten pro Datei, kein gemeinsames Frontend-Framework darüber:

| Datei | Zweck |
|---|---|
| `cart.js` | Warenkorb, rein clientseitig über `localStorage` |
| `barcode-camera.js` | Kamera-Scan-Steuerung (Start/Stop/Vibration), nutzt `html5-qrcode` |
| `signature.js` | Unterschrift-Canvas für Ausgabe-Bestätigung |
| `form-guard.js` | Doppel-Submit-Schutz (`data-guard`-Attribut) |
| `qty-stepper.js` | Mengen-Stepper statt nackter Zahlenfelder |
| `view-toggle.js` | Kachel-/Listenansicht-Umschalter |
| `lightbox.js` | Klick-Vorschau für Gegenstands-/Material-Bilder |
| `offline-banner.js` | reiner Hinweis-Banner bei fehlender Verbindung |

Neue clientseitige Logik folgt demselben Muster: eine Datei, ein
Verantwortungsbereich, kein Einstieg eines neuen Frameworks ohne triftigen
Grund (siehe `CLAUDE.md` "Abhängigkeiten").

## Design-System

Ein einziges CSS-File, `app/static/css/app.css`, mit CSS Custom Properties
(`--space-*`, `--brand`, `--ink`, ...) statt eines CSS-Frameworks. Leitmotiv
"Werkstatt-Inventaranhänger" (Tag-Card-Optik mit Perforationskante).
Typografie: Trebuchet MS als Systemfont (kein externer Font-Import, siehe
`docs/security/secrets.md`).

Wiederkehrende Layout-Bausteine:

- `.settings-row` / `.settings-list` - kompakte Zeilenliste (Benutzer,
  Abteilungen, Presets, Papierkorb, ...)
- `.item-card` / `.item-grid` - Kachel- und Listenansicht für Gegenstände/
  Material, per `.view-list`-Modifier umschaltbar
- `.tag-card` - die "Anhänger"-Karte für Formulare/Login/Badges

**Wichtige Lektion (siehe `CHANGELOG.md` 0.23.1):** ein `<details>`-Element
NICHT gleichzeitig mit einer bestehenden flexbasierten Zeilen-Klasse (wie
`.settings-row`) UND einer eigenen Display-Override-Klasse versehen -
Chrome/Firefox überschreiben das wie erwartet, Safari/WebKit rendert diese
Kombination nachweislich anders. Ein eigenständiges, unbeteiligtes
`<details>` neben der normalen Zeile ist robuster als der Versuch, die Zeile
selbst aufklappbar zu machen.

## Mobile/PWA

Bottom-Tab-Bar unterhalb eines Breakpoints (siehe `app.css`), volle Top-Nav
darüber - kein separates Mobile-Template, dieselben Jinja-Templates für
beide. Installierbare PWA (`manifest.webmanifest`), Service Worker
(`app/static/sw.js`) cached ausschließlich die statische App-Shell
(`/static/...`) network-first - bewusst KEIN Cache für Seiten-Navigationen
oder API-Antworten (Risiko: veraltete Bestands-/Verfügbarkeitsdaten offline
anzeigen). Cache-Busting für alle `/static/...`-URLs hängt an
`app.version.__version__` (`?v=...`) - **muss bei jeder CSS/JS-relevanten
Änderung mitgezogen werden**, sonst bleiben Browser mit bereits gecachtem
CSS/JS auf altem Stand (siehe `CHANGELOG.md` 0.23.0/0.23.1 für den Vorfall).

## Barrierefreiheit/Bedienung

44px Mindesthöhe für Touch-Targets, `:focus-visible`-Ring als Pflicht (siehe
`app.css`), native HTML-Elemente (`<details>`, `<select>`) statt
nachgebauter Custom-Widgets wo möglich - weniger eigener JS-Code, bessere
Tastatur-/Screenreader-Unterstützung geschenkt.
