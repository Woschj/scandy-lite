# OWASP-Absicherung: Stand &amp; Vorgehen

Bei jeder Änderung, die Nutzereingaben, Auth oder Dateizugriff berührt, auf
die OWASP-Top-10-relevanten Punkte prüfen (siehe `CLAUDE.md`). Stand in
diesem Projekt, damit klar ist, was schon abgedeckt ist und was nicht:

## SQL-Injection

Durchgängig parametrisierte Queries über SQLModel/SQLAlchemy. Die wenigen
Stellen mit `text(...)` (`app/main.py` Health-Check `SELECT 1`,
`app/models/lending.py` statischer partieller Index) enthalten **keine**
Nutzereingaben - kein String-Interpolation-Pattern für SQL im Projekt.
Neue rohe SQL-Fragmente sind ein Warnsignal, nicht die Norm.

## XSS

Jinja2-Autoescaping ist Standard und wird nicht abgeschaltet
(`| safe`/`Markup` nur mit triftigem Grund und dann mit Kommentar, warum
der Wert vertrauenswürdig ist). Nutzereingaben (Item-Namen, Notizen, ...)
landen unverändert escaped im Template.

## CSRF

Eigener Token (kein Framework-Default), siehe `app/core/security.py`
(`generate_csrf_token`/`verify_csrf_token`) und `app/core/deps.py`
(`verify_csrf`-Dependency). Jedes state-changing Formular bindet
`partials/csrf_field.html` ein. `SameSite=Lax` auf dem Session-Cookie ist
eine zusätzliche Schicht, kein Ersatz für den Token.

## Path Traversal

Datei-Uploads nutzen die Entity-UUID als Dateiname, nie nutzergesteuerten
Text (siehe `docs/security/secrets.md`).

## Command Injection / SSRF

Keine Stellen im Code, die Nutzereingaben an eine Shell oder einen
HTTP-Client mit nutzergesteuerter URL übergeben. Beim Hinzufügen einer
Funktion, die eine URL/einen Pfad von außen entgegennimmt (Import-Feature,
Webhook, ...), explizit prüfen, ob das eine neue SSRF-Fläche öffnet.

## Broken Authentication

bcrypt für Passwort-Hashes, Rate-Limiting auf Login/Passwort-Reset (siehe
`docs/architecture/auth.md`), Passwort-Reset-Tokens einmal verwendbar und
zeitlich begrenzt, `httponly`+`SameSite=Lax`-Session-Cookie.

## Hardcoded Secrets

Siehe `docs/security/secrets.md` - Fail-Fast statt Default-Werten in
Produktion.

## Bekannte Lücken (nicht ignorieren, bewusst dokumentiert)

- **Kein Content-Security-Policy-Header** gesetzt. Vor dem Nachrüsten
  prüfen, ob das mit den selbst gehosteten Vendor-Skripten
  (`app/static/js/vendor/`) und Inline-`<script>`-Blöcken in den
  Templates kollidiert (mehrere Templates nutzen kleine Inline-Scripts).
- **Kein automatisiertes Security-Scanning in der CI** (`.github/workflows/
  ci.yml` läuft Tests + Docker-Build-Check, kein `pip-audit`/`safety`/
  SAST-Schritt). Bei neuen Abhängigkeiten (siehe `CLAUDE.md`
  "Abhängigkeiten") manuell auf bekannte CVEs prüfen.

Neue Lücken, die bewusst zurückgestellt werden (Aufwand/Nutzen-Abwägung
für ein internes Tool), gehören in diese Liste statt stillschweigend im
Code zu verschwinden - nur so bleibt nachvollziehbar, was eine bewusste
Entscheidung war und was schlicht vergessen wurde.
