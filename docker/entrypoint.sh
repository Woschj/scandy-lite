#!/bin/sh
# Entrypoint fÃ¼r den App-Container:
#   1. Warten, bis Postgres erreichbar ist
#   2. Alembic-Migrationen anwenden (Schema ist danach immer aktuell)
#   3. Optional: ersten Admin-User + Default-Abteilung anlegen
#      (nur wenn ADMIN_USERNAME/ADMIN_PASSWORD gesetzt sind - praktisch fÃ¼r
#      ein Plug-and-Play-Portainer-Deployment, ohne dass man in den
#      Container exec'en muss)
#   4. Ãœbergebenes CMD ausfÃ¼hren (uvicorn)
set -e

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
  echo "[entrypoint] PrÃ¼fe Admin-Bootstrap fÃ¼r '$ADMIN_USERNAME'..."
  python -m scripts.seed_admin \
    --username "$ADMIN_USERNAME" \
    --password "$ADMIN_PASSWORD" \
    --department-code "${DEFAULT_DEPARTMENT_CODE:-werkstatt}" \
    --department-name "${DEFAULT_DEPARTMENT_NAME:-Werkstatt}"
else
  echo "[entrypoint] ADMIN_USERNAME/ADMIN_PASSWORD nicht gesetzt - Ã¼berspringe Admin-Bootstrap."
fi

echo "[entrypoint] Starte Anwendung..."
exec "$@"
