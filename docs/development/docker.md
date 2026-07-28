# Docker

## Image

Multi-Stage-`Dockerfile`: `builder`-Stage installiert Dependencies in ein
venv, `runtime`-Stage (`python:3.12-slim`) kopiert nur das fertige venv +
den Anwendungscode - kein Compiler/Build-Toolchain im finalen Image.
Läuft als **non-root** (`useradd ... scandy`, `USER scandy`), nicht als
root. `HEALTHCHECK` ist Teil des Images (`--interval=30s ... --retries=5`),
kein separater externer Check nötig, damit Docker/Portainer den
Container-Status korrekt anzeigt.

## Compose-Dateien

| Datei | Zweck |
|---|---|
| `compose.yaml` | Produktiv-Stack: `app` + `db` (Postgres) + optionaler `caddy` (HTTPS-Reverse-Proxy, nötig für Kamera-Zugriff) |
| `compose.dev.yaml` | nur `db`, für lokale Entwicklung mit `uvicorn --reload` gegen echtes Postgres |
| `compose.secrets.yaml` | optionales Overlay für Docker/Swarm-Secrets statt Umgebungsvariablen, siehe `docs/security/secrets.md` |

## Entrypoint

`docker/entrypoint.sh` macht bei jedem Container-Start, in dieser
Reihenfolge: Secrets auflösen (`*_FILE`-Konvention) → warten, bis Postgres
bereit ist → `alembic upgrade head` → Admin-User + Default-Abteilung
anlegen, falls `ADMIN_USERNAME`/`ADMIN_PASSWORD` gesetzt sind und noch
kein Admin existiert → App starten. Kein manueller Migrations-Schritt bei
einem Redeploy nötig.

## Healthcheck &amp; Startup

`GET /health` ist der Healthcheck-Endpunkt (siehe `app/main.py`) - prüft
u. a. eine echte DB-Verbindung (`SELECT 1`). Skripte, die auf "App ist
bereit" warten (z. B. `install.sh`), pollen diesen Endpunkt statt fest
eine Wartezeit zu verstreichen zu lassen.

## Lokale Entwicklung ohne vollen Stack

`docker compose -f compose.dev.yaml up -d` (nur Postgres) +
`uvicorn app.main:app --reload` direkt auf dem Host - schnelleres
Reload als ein kompletter Image-Rebuild bei jeder Änderung. Für einen
kompletten, produktionsnahen Test: `./install.sh` (siehe `README.md`,
baut und startet den vollen Stack inkl. generierter `.env`).

## Neue Container-Services

Ein neuer Service (z. B. ein zusätzlicher Worker-Prozess) sollte
denselben Prinzipien folgen: non-root, Healthcheck, Secrets über Env-Var
oder `*_FILE`, keine Ports nach außen veröffentlichen, die nicht wirklich
von außerhalb des Docker-Netzwerks gebraucht werden (siehe `db` in
`compose.yaml` - kein Port-Publish, nur der `app`-Container braucht
Zugriff).
