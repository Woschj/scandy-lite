# Scandy-Lite

Schlanke Ausleihe/Ausgabe-Verwaltung für Werkzeuge und Verbrauchsmaterial,
mit Mehr-Abteilungs-Unterstützung. Extrahiert und clean neu aufgebaut aus
[scandy2](https://github.com/woschj/scandy2), reduziert auf den Kern-Workflow
(kein Ticketsystem, kein Kantinenplan, keine Job-Verwaltung).

## Tech-Stack

- **Backend:** FastAPI (async)
- **Datenbank:** PostgreSQL + SQLModel + Alembic-Migrationen
- **Frontend:** HTMX + Alpine.js, eigenes Design-System (Grundlage steht, Item-Listen folgen Phase 3+)
- **Mobile:** PWA (installierbar, responsive), Kamera-Barcode-Scan folgt Phase 4
- **Auth:** lokal (Phase 1), LDAP/SSO andockbar ohne Schema-Umbau (siehe unten)

## Projektstatus

- [x] **Phase 1 — Datenmodell + DB-Layer**
- [x] **Phase 2 — Auth + Abteilungs-Scoping + Frontend-Fundament**
- [x] **Phase 3 — CRUD für Gegenstände/Verbrauchsmaterial/Mitarbeiter** (dieser Stand)
- [ ] Phase 4 — Ausleihe/Rückgabe-Logik + Barcode-Scan-Endpoint
- [ ] Phase 5 — Historie-Ansicht
- [ ] Phase 6 — Feinschliff UI/PWA (Offline-Hinweis, Service Worker)
- [x] **Phase 7 — Docker-Setup für Produktivbetrieb** (vorgezogen für Portainer-Deployment)

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
| `APP_PORT` | Port, unter dem die App erreichbar ist | `8000` |
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
