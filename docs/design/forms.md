# Formulare

## Grundmuster

Normale HTML-`<form method="post">`, kein clientseitiges Formular-
Framework (kein React Hook Form o. Ä.). Jedes state-changing Formular
enthält `{% include "partials/csrf_field.html" %}` (siehe
`docs/security/owasp.md`). Validierung serverseitig; HTML5-Attribute
(`required`, `type="email"`, `accept="image/..."`) als zusätzliche,
clientseitige Vorab-Prüfung - kein Ersatz für die Server-Validierung.

## Fehleranzeige

Ein Formular liefert bei Validierungsfehlern die Eingabeseite mit
`error`-Kontextvariable erneut aus (`<div class="form-error" role="alert">`),
**mit den bereits eingegebenen Werten** über das `fv`-Dict (`fv.get(...)`).
Ein bekannter, behobener Fehler: Formulare verloren früher bei einem
doppelten Barcode alle bereits eingegebenen Werte (Name, Kategorie,
Standort, Notizen), nicht nur den Barcode selbst - beim Ergänzen neuer
Validierungsfehler immer prüfen, dass `fv` alle Felder abdeckt, nicht nur
das zuletzt geänderte.

## Wiederkehrende Bausteine

- **`.field`** - Label + Input/Select, einheitlicher Abstand.
- **Scanner-Eingabe:** `data-scanner-enter="next"` auf Barcode-Feldern -
  ein angeschlossener Hardware-Scanner sendet Enter nach dem Scan, dieses
  Attribut springt zum nächsten Feld statt das Formular sofort abzusenden.
- **Doppel-Submit-Schutz:** `data-guard`-Attribut (`form-guard.js`) auf
  Formularen, deren doppeltes Absenden ein Problem wäre (Ausleihe/
  Rückgabe/Entnahme/Ausgabe-Bestätigung). **Event-Phasen-Falle:** ein
  Capture-Phase-Listener (Doppel-Submit-Schutz) feuert VOR einem
  Bubble-Phase-Listener (z. B. Unterschrift-Validierung in
  `signature.js`) - bricht Letzterer die Übermittlung ab, darf der
  Button nicht schon dauerhaft gesperrt sein. Lösung im bestehenden Code:
  Bubble-Phase + `e.defaultPrevented`-Prüfung, siehe `form-guard.js`.
- **Mengenfelder:** `qty-stepper.js` statt nackter `<input type="number">`
  - konsistente Bedienung auf Touch-Geräten.
- **Datei-Uploads (Bilder):** eigenes Formular pro Upload-Aktion (siehe
  `app/templates/items/form.html`, `enctype="multipart/form-data"`), nicht
  Teil des Haupt-Formulars - erlaubt "Bild ändern", ohne den Rest des
  Datensatzes erneut abzusenden.

## Neue Formulare

Vor dem Bauen eines neuen Formulars: gibt es bereits ein vergleichbares
(Item-Form, User-Form) - Feld-Markup, Fehleranzeige und CSRF-Handling von
dort übernehmen statt neu zu erfinden.
