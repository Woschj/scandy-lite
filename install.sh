#!/bin/sh
# Scandy-Lite Erstinstallation (Linux/Mac).
#
# Macht aus einem frischen "git clone" eine laufende Instanz:
#   1. Prüft Docker/Docker Compose
#   2. Erzeugt .env mit zufälligen Secrets, falls noch keine existiert
#      (idempotent - ein erneuter Lauf verändert eine bestehende .env NICHT)
#   3. Baut und startet den Stack
#   4. Wartet, bis die App tatsächlich antwortet
#   5. Zeigt Zugangs-URL + Admin-Zugangsdaten an
#
# Nutzung:
#   ./install.sh
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Scandy-Lite Installation ==="
echo ""

# --- 1. Voraussetzungen ---------------------------------------------------
if ! command -v docker >/dev/null 2>&1; then
  echo "FEHLER: Docker wurde nicht gefunden. Installation: https://docs.docker.com/get-docker/" >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "FEHLER: 'docker compose' (Compose V2) ist nicht verfügbar." >&2
  echo "        Ältere docker-compose-Standalone-Installationen reichen nicht - Docker Desktop/Engine aktualisieren." >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "FEHLER: openssl wird zum Erzeugen der Zugangsdaten gebraucht, ist aber nicht installiert." >&2
  exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "FEHLER: curl wird für die Start-Überprüfung gebraucht, ist aber nicht installiert." >&2
  exit 1
fi

# --- 2. .env erzeugen (nur falls noch keine existiert) --------------------
if [ -f .env ]; then
  echo ".env existiert bereits - wird unverändert weiterverwendet."
else
  echo "Erzeuge .env mit zufällig generierten Zugangsdaten..."
  SECRET_KEY="$(openssl rand -hex 32)"
  POSTGRES_PASSWORD="$(openssl rand -hex 24)"
  ADMIN_PASSWORD="$(openssl rand -hex 8)"

  cat > .env <<ENVEOF
# Automatisch von install.sh generiert am $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Zufällige, sichere Werte - siehe INSTALL.md für die Bedeutung der einzelnen
# Variablen. ADMIN_PASSWORD nach dem ersten erfolgreichen Login idealerweise
# aus dieser Datei entfernen (liegt aktuell im Klartext).
SECRET_KEY=$SECRET_KEY
POSTGRES_USER=scandy
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=scandy_lite
ACCESS_TOKEN_EXPIRE_MINUTES=720
SESSION_COOKIE_SECURE=false
ADMIN_USERNAME=admin
ADMIN_PASSWORD=$ADMIN_PASSWORD
DEFAULT_DEPARTMENT_CODE=werkstatt
DEFAULT_DEPARTMENT_NAME=Werkstatt
APP_PORT=8000
APP_HTTPS_PORT=8443
ENVEOF
  echo ".env erzeugt."
fi

# .env für die Werte unten einlesen (funktioniert unabhängig davon, ob sie
# gerade neu erzeugt oder schon vorhanden war)
# shellcheck disable=SC1091
set -a
. ./.env
set +a

# --- 3. Bauen und starten --------------------------------------------------
echo ""
echo "Baue und starte Container (kann beim allerersten Mal 1-2 Minuten dauern)..."
docker compose up -d --build

# --- 4. Auf tatsächlich antwortende App warten -----------------------------
echo ""
echo "Warte auf App-Start..."
ATTEMPTS=0
MAX_ATTEMPTS=60
until curl -sf "http://localhost:${APP_PORT:-8000}/health" >/dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ "$ATTEMPTS" -ge "$MAX_ATTEMPTS" ]; then
    echo "" >&2
    echo "App antwortet nach 2 Minuten immer noch nicht. Logs prüfen mit:" >&2
    echo "  docker compose logs app" >&2
    exit 1
  fi
  sleep 2
done

# --- 5. Zusammenfassung -----------------------------------------------------
echo ""
echo "=== Fertig! ==="
echo ""
echo "App erreichbar unter:  http://localhost:${APP_PORT:-8000}"
echo "Login:                 ${ADMIN_USERNAME:-admin} / ${ADMIN_PASSWORD}"
echo ""
echo "Für Kamera-Scan (benötigt HTTPS): https://localhost:${APP_HTTPS_PORT:-8443}"
echo "(zeigt eine Zertifikatswarnung - selbstsigniert, einmalig pro Gerät bestätigen)"
echo ""
echo "Zugangsdaten stehen auch in .env - ADMIN_PASSWORD danach am besten dort"
echo "entfernen (liegt aktuell im Klartext, wird beim nächsten Start nicht erneut"
echo "gebraucht - das Admin-Konto existiert dann schon)."
