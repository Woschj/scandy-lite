#!/bin/sh
# Entrypoint für den App-Container:
#   0. Docker-Secrets auflösen (siehe unten) - optional, wirkt sich nur aus,
#      wenn *_FILE-Variablen gesetzt sind
#   1. Warten, bis Postgres erreichbar ist
#   2. Alembic-Migrationen anwenden (Schema ist danach immer aktuell)
#   3. Optional: ersten Admin-User + Default-Abteilung anlegen
#      (nur wenn ADMIN_USERNAME/ADMIN_PASSWORD gesetzt sind - praktisch für
#      ein Plug-and-Play-Portainer-Deployment, ohne dass man in den
#      Container exec'en muss)
#   4. Übergebenes CMD ausführen (uvicorn)
set -e

# --- Docker/Swarm-Secrets: optionale *_FILE-Konvention -------------------
# Für jede der drei sensiblen Variablen kann statt des Klartext-Werts eine
# "<NAME>_FILE"-Variable auf eine gemountete Datei zeigen (Docker-Secrets
# landen z.B. unter /run/secrets/<name>) - der Dateiinhalt wird dann anstelle
# der Variable selbst verwendet. Ohne *_FILE-Variablen ändert sich nichts am
# bisherigen Verhalten (Klartext-Env-Var bzw. compose.yaml-Fallback).
resolve_secret() {
  var_name="$1"
  eval "file_path=\${${var_name}_FILE:-}"
  if [ -n "$file_path" ]; then
    if [ ! -f "$file_path" ]; then
      echo "[entrypoint] ${var_name}_FILE=$file_path gesetzt, aber Datei nicht gefunden - Abbruch." >&2
      exit 1
    fi
    eval "$var_name=\$(cat "$file_path")"
    export "$var_name"
    echo "[entrypoint] $var_name aus Secret-Datei ($file_path) geladen."
  fi
}

resolve_secret SECRET_KEY
resolve_secret POSTGRES_PASSWORD
resolve_secret ADMIN_PASSWORD

# Kam POSTGRES_PASSWORD gerade frisch aus einer Secret-Datei, DATABASE_URL(_SYNC)
# neu zusammensetzen - compose.yaml hätte sonst schon vorher (beim Start des
# Containers, per YAML-Variableninterpolation) die Verbindungs-Strings mit dem
# UNAUFGELÖSTEN Wert bzw. dessen unsicherem Fallback gebaut, da Compose selbst
# keine Secrets in String-Interpolation einsetzen kann.
if [ -n "${POSTGRES_PASSWORD_FILE:-}" ]; then
  DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER:-scandy}:${POSTGRES_PASSWORD}@${POSTGRES_HOST:-db}:5432/${POSTGRES_DB:-scandy_lite}"
  DATABASE_URL_SYNC="postgresql+psycopg2://${POSTGRES_USER:-scandy}:${POSTGRES_PASSWORD}@${POSTGRES_HOST:-db}:5432/${POSTGRES_DB:-scandy_lite}"
  export DATABASE_URL DATABASE_URL_SYNC
fi

echo "[entrypoint] Warte auf Datenbank..."
python <<'PY'
import sys
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings

settings = get_settings()

for attempt in range(1, 31):
    try:
        engine = create_engine(settings.DATABASE_URL_SYNC)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[entrypoint] Datenbank erreichbar.")
        break
    except OperationalError:
        print(f"[entrypoint] Datenbank noch nicht bereit ({attempt}/30) ...")
        time.sleep(2)
else:
    print("[entrypoint] Datenbank nach 60s nicht erreichbar - Abbruch.", file=sys.stderr)
    sys.exit(1)
PY

echo "[entrypoint] Wende Migrationen an..."
alembic upgrade head

if [ -n "$ADMIN_USERNAME" ] && [ -n "$ADMIN_PASSWORD" ]; then
  echo "[entrypoint] Prüfe Admin-Bootstrap für '$ADMIN_USERNAME'..."
  python -m scripts.seed_admin \
    --username "$ADMIN_USERNAME" \
    --password "$ADMIN_PASSWORD" \
    --department-code "${DEFAULT_DEPARTMENT_CODE:-werkstatt}" \
    --department-name "${DEFAULT_DEPARTMENT_NAME:-Werkstatt}"
else
  echo "[entrypoint] ADMIN_USERNAME/ADMIN_PASSWORD nicht gesetzt - überspringe Admin-Bootstrap."
fi

echo "[entrypoint] Starte Anwendung..."
exec "$@"
