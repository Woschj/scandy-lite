#!/usr/bin/env bash
# Sichert Datenbank + Uploads - funktioniert automatisch sowohl gegen die
# Docker/Portainer-Installation als auch gegen die native Proxmox-VE-LXC-
# Installation (siehe INSTALL.md), ohne dass man wissen muss, welche der
# beiden gerade läuft.
#
# Erkennung: läuft im aktuellen Verzeichnis ein Docker-Compose-Service
# namens "db", wird der Docker-Weg genutzt (pg_dump/tar über
# `docker compose exec`, funktioniert unabhängig vom Compose-Projektnamen -
# das ist genau das, was beim manuellen Vorgehen leicht zu Fehlern führt,
# siehe INSTALL.md-Hinweis zu Volume-Namen). Sonst wird die native LXC-
# Installation angenommen (erfordert root + lokalen PostgreSQL-Zugriff).
#
# Nutzung (im Repo-Verzeichnis, bzw. auf der LXC in /opt/scandy-lite):
#   ./scripts/backup.sh
#
# Legt zwei Dateien in ./backups/ an:
#   scandy_lite_<timestamp>.sql.gz          - Datenbank
#   scandy_lite_<timestamp>_uploads.tar.gz  - hochgeladene Bilder

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

STAMP="$(date +%Y%m%d_%H%M%S)"
mkdir -p backups
DB_DUMP="backups/scandy_lite_${STAMP}.sql.gz"
UPLOADS_DUMP="backups/scandy_lite_${STAMP}_uploads.tar.gz"

is_docker_mode() {
  [ -f compose.yaml ] && command -v docker >/dev/null 2>&1 \
    && docker compose version >/dev/null 2>&1 \
    && docker compose ps --status running --services 2>/dev/null | grep -qx db
}

env_var() {
  # env_var NAME <.env - liest NAME=... aus der .env, ohne sie komplett einzulesen
  grep -E "^$1=" .env 2>/dev/null | head -n1 | cut -d= -f2-
}

if is_docker_mode; then
  echo "Docker-Modus erkannt."
  POSTGRES_USER="$(env_var POSTGRES_USER)"
  POSTGRES_DB="$(env_var POSTGRES_DB)"
  POSTGRES_USER="${POSTGRES_USER:-scandy}"
  POSTGRES_DB="${POSTGRES_DB:-scandy_lite}"

  echo "Sichere Datenbank..."
  docker compose exec -T db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip >"$DB_DUMP"

  echo "Sichere Uploads..."
  docker compose exec -T app tar czf - -C /app/uploads . >"$UPLOADS_DUMP"
else
  if [ "$(id -u)" -ne 0 ] || ! command -v pg_dump >/dev/null 2>&1 || [ ! -f .env ]; then
    echo "FEHLER: Weder eine laufende Docker-Installation gefunden (kein 'db'-Service aktiv), noch sieht das hier nach der nativen LXC-Installation aus (als root im Repo-Verzeichnis mit .env ausführen, z.B. in /opt/scandy-lite)." >&2
    exit 1
  fi
  echo "Native Installation (LXC) erkannt."
  DB_URL="$(env_var DATABASE_URL)"
  DB_NAME="$(echo "$DB_URL" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"

  echo "Sichere Datenbank..."
  sudo -u postgres pg_dump "$DB_NAME" | gzip >"$DB_DUMP"

  echo "Sichere Uploads..."
  tar czf "$UPLOADS_DUMP" -C uploads .
fi

chmod 600 "$DB_DUMP" "$UPLOADS_DUMP"

echo ""
echo "Fertig:"
echo "  $DB_DUMP"
echo "  $UPLOADS_DUMP"
echo ""
echo "Wiederherstellen mit: ./scripts/restore.sh $DB_DUMP"
