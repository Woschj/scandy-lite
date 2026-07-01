# Scandy-Lite

Schlanke Ausleihe/Ausgabe-Verwaltung für Werkzeuge und Verbrauchsmaterial,
mit Mehr-Abteilungs-Unterstützung. Extrahiert und clean neu aufgebaut aus
[scandy2](https://github.com/woschj/scandy2), reduziert auf den Kern-Workflow
(kein Ticketsystem, kein Kantinenplan, keine Job-Verwaltung).

## Tech-Stack

- **Backend:** FastAPI (async)
- **Datenbank:** PostgreSQL + SQLModel + Alembic-Migrationen
- **Frontend:** HTMX + Alpine.js (folgt in späterer Phase)
- **Mobile:** PWA mit Kamera-basiertem Barcode-Scan (folgt in späterer Phase)
- **Auth:** lokal (Phase 1), LDAP/SSO andockbar ohne Schema-Umbau (siehe unten)

## Projektstatus

- [x] **Phase 1 — Datenmodell + DB-Layer**
- [x] **Phase 2 — Auth + Abteilungs-Scoping + Frontend-Fundament** (dieser Stand)
- [ ] Phase 3 — CRUD für Tools/Consumables/Workers
- [ ] Phase 4 — Ausleihe/Rückgabe-Logik + Barcode-Scan-Endpoint
- [ ] Phase 5 — Historie-Ansicht
- [ ] Phase 6 — Feinschliff UI/PWA (Offline-Hinweis, Service Worker)
- [ ] Phase 7 — Docker-Setup für Produktivbetrieb

## Design-System

Signatur-Element: Karten im Look physischer Werkstatt-Inventaranhänger (Asset-Tags)
mit Perforationskante und Barcode-Streifen — zieht sich durch Login, Dashboard und
später durch alle Item-Karten. Typografie: **IBM Plex Mono** (Labels, Status, Barcodes)
+ **IBM Plex Sans** (Fließtext). Responsive: Top-Nav am Desktop, Bottom-Tab-Bar mobil
(Daumen-erreichbar, `env(safe-area-inset-bottom)`-sicher). PWA-Manifest + Icons bereits
vorhanden, Installierbarkeit kommt final in Phase 6 (Service Worker für Offline-Shell).

## Erster Login (nach `alembic upgrade head`)

```bash
python -m scripts.seed_admin --username admin --password <sicheres-passwort> \
  --department-code werkstatt --department-name Werkstatt
```

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

## Lokales Setup

```bash
# 1. Postgres starten
docker compose up -d

# 2. Virtualenv + Dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 3. .env anlegen
cp .env.example .env

# 4. Migrationen anwenden
alembic upgrade head

# 5. App starten
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
