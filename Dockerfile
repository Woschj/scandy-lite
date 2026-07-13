# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# libpq5 für psycopg2 (Alembic-Migrationen laufen synchron), curl für den Healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# BuildKit-Cache-Mount statt PIP_NO_CACHE_DIR: pip's Wheel-Cache liegt AUSSERHALB
# der Image-Layer (bläht das Image nicht auf), bleibt aber über mehrere Builds
# hinweg erhalten - eine Änderung an requirements.txt lädt dadurch nur noch
# tatsächlich neue/geänderte Pakete neu, statt alle ~15 Abhängigkeiten jedes
# Mal komplett neu herunterzuladen.
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt

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
