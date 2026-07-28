#!/usr/bin/env bash
# Stellt ein mit scripts/backup.sh erstelltes Backup wieder her.
#
# ACHTUNG: ersetzt die komplette aktuelle Datenbank (und, falls gefunden,
# alle Uploads) unwiederbringlich durch den Inhalt des Backups. Fragt vor
# dem eigentlichen Wiederherstellen eine Bestätigung ab.
#
# Erkennung Docker vs. native LXC wie in backup.sh.
#
# Nutzung (im Repo-Verzeichnis, bzw. auf der LXC in /opt/scandy-lite):
#   ./scripts/restore.sh backups/scandy_lite_20260724_213000.sql.gz
#
# Das zugehörige "..._uploads.tar.gz" wird automatisch danebenliegend
# gesucht (gleicher Zeitstempel) - falls nicht vorhanden, wird nur die
# Datenbank wiederhergestellt, Uploads bleiben unverändert. Alternativ als
# zweites Argument explizit angeben.

set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

DB_DUMP="${1:-}"
UPLOADS_DUMP="${2:-}"

if [ -z "$DB_DUMP" ] || [ ! -f "$DB_DUMP" ]; then
  echo "Nutzung: $0 <db-dump.sql.gz> [uploads-dump.tar.gz]" >&2
  echo "" >&2
  echo "Verfügbare Backups in ./backups/:" >&2
  ls -1 backups/*.sql.gz 2>/dev/null >&2 || echo "  (keine gefunden)" >&2
  exit 1
fi

if [ -z "$UPLOADS_DUMP" ]; then
  UPLOADS_DUMP="${DB_DUMP%.sql.gz}_uploads.tar.gz"
fi
if [ ! -f "$UPLOADS_DUMP" ]; then
  echo "Hinweis: Uploads-Backup '$UPLOADS_DUMP' nicht gefunden - es wird nur die Datenbank wiederhergestellt, Bilder bleiben unverändert."
  UPLOADS_DUMP=""
fi

echo "=== ACHTUNG ==="
echo "Dies ERSETZT die komplette aktuelle Datenbank$([ -n "$UPLOADS_DUMP" ] && echo " und alle Uploads") unwiederbringlich."
echo "Datenbank-Backup: $DB_DUMP"
[ -n "$UPLOADS_DUMP" ] && echo "Uploads-Backup:   $UPLOADS_DUMP"
echo ""
read -r -p "Zum Bestätigen 'JA' eintippen: " CONFIRM
if [ "$CONFIRM" != "JA" ]; then
  echo "Abgebrochen."
  exit 1
fi

is_docker_mode() {
  [ -f compose.yaml ] && command -v docker >/dev/null 2>&1 \
    && docker compose version >/dev/null 2>&1 \
    && docker compose ps --status running --services 2>/dev/null | grep -qx db
}

env_var() {
  grep -E "^$1=" .env 2>/dev/null | head -n1 | cut -d= -f2-
}

if is_docker_mode; then
  echo "Docker-Modus erkannt."
  POSTGRES_USER="$(env_var POSTGRES_USER)"
  POSTGRES_DB="$(env_var POSTGRES_DB)"
  POSTGRES_USER="${POSTGRES_USER:-scandy}"
  POSTGRES_DB="${POSTGRES_DB:-scandy_lite}"

  echo "Stoppe App..."
  docker compose stop app

  echo "Stelle Datenbank wieder her..."
  docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\";"
  docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres \
    -c "CREATE DATABASE \"$POSTGRES_DB\" WITH OWNER \"$POSTGRES_USER\" ENCODING 'UTF8' TEMPLATE template0;"
  gunzip -c "$DB_DUMP" | docker compose exec -T db psql -U "$POSTGRES_USER" "$POSTGRES_DB"

  if [ -n "$UPLOADS_DUMP" ]; then
    echo "Stelle Uploads wieder her..."
    docker compose exec -T app sh -c 'rm -rf /app/uploads/* /app/uploads/.[!.]* 2>/dev/null; true'
    gunzip -c "$UPLOADS_DUMP" | docker compose exec -T app tar xzf - -C /app/uploads
  fi

  # docker/entrypoint.sh wendet beim Start automatisch "alembic upgrade head"
  # an (siehe Dockerfile/ENTRYPOINT) - kein separater Migrations-Schritt hier
  # nötig, nur der App-Container muss wieder hochgefahren werden.
  echo "Starte App..."
  docker compose start app
else
  if [ "$(id -u)" -ne 0 ] || ! command -v pg_dump >/dev/null 2>&1 || [ ! -f .env ]; then
    echo "FEHLER: Weder eine laufende Docker-Installation gefunden (kein 'db'-Service aktiv), noch sieht das hier nach der nativen LXC-Installation aus (als root im Repo-Verzeichnis mit .env ausführen, z.B. in /opt/scandy-lite)." >&2
    exit 1
  fi
  echo "Native Installation (LXC) erkannt."
  DB_URL="$(env_var DATABASE_URL)"
  DB_USER="$(echo "$DB_URL" | sed -E 's#.*://([^:]+):.*#\1#')"
  DB_NAME="$(echo "$DB_URL" | sed -E 's#.*/([^/?]+)(\?.*)?$#\1#')"

  echo "Stoppe Dienste..."
  systemctl stop scandy-lite scandy-lite-https

  echo "Stelle Datenbank wieder her..."
  sudo -u postgres psql -c "DROP DATABASE IF EXISTS \"$DB_NAME\";"
  sudo -u postgres psql -c "CREATE DATABASE \"$DB_NAME\" WITH OWNER \"$DB_USER\" ENCODING 'UTF8' TEMPLATE template0;"
  gunzip -c "$DB_DUMP" | sudo -u postgres psql "$DB_NAME"

  if [ -n "$UPLOADS_DUMP" ]; then
    echo "Stelle Uploads wieder her..."
    rm -rf uploads
    mkdir -p uploads
    tar xzf "$UPLOADS_DUMP" -C uploads
  fi

  echo "Wende Migrationen an (falls das Backup von einem älteren App-Stand ist)..."
  venv/bin/alembic upgrade head

  echo "Starte Dienste..."
  systemctl start scandy-lite scandy-lite-https
fi

echo ""
echo "Fertig."
