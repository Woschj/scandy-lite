# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: Builder - installiert die Python-Abhängigkeiten in ein eigenes venv.
# Keine der requirements.txt-Pakete braucht einen Compiler (alle liefern
# fertige Wheels für linux/amd64+arm64) - trotzdem als eigene Stage, damit
# NICHTS von pip's Zwischenzustand (Download-Cache, __pycache__ aus der
# Installation, apt-Metadaten falls doch mal ein Paket kompilieren muss) im
# fertigen Runtime-Image landet. Kleineres, aufgeräumteres Image als bei
# einem einzelnen COPY . . + pip install im selben Layer.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt .
# BuildKit-Cache-Mount statt PIP_NO_CACHE_DIR: pip's Wheel-Cache liegt AUSSERHALB
# der Image-Layer (bläht das Image nicht auf), bleibt aber über mehrere Builds
# hinweg erhalten - eine Änderung an requirements.txt lädt dadurch nur noch
# tatsächlich neue/geänderte Pakete neu, statt alle Abhängigkeiten jedes
# Mal komplett neu herunterzuladen.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt


# ---------------------------------------------------------------------------
# Stage 2: Runtime - frisches, schlankes Image. Nur das fertige venv +
# App-Code werden übernommen, kein pip-Cache, keine Build-Zwischenstände.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

# libpq5 für psycopg2 (Alembic-Migrationen laufen synchron), curl für den Healthcheck.
# Nur Runtime-Bibliothek (libpq5), keine -dev-Variante nötig - es wird ja nichts
# mehr kompiliert, das passiert alles schon in der Builder-Stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv
COPY . .
RUN chmod +x docker/entrypoint.sh

# Kein Root-User im Container
RUN useradd --create-home --uid 1000 scandy \
    && mkdir -p /app/uploads \
    && chown -R scandy:scandy /app
USER scandy

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -f http://localhost:8000/health || exit 1

ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
