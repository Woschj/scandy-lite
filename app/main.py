"""
Scandy-Lite - FastAPI-Einstiegspunkt.

Phase 1: nur Grundgerüst + Health-Check, damit DB-Layer und Modelle sich
verifizieren lassen. Router (Auth, Tools, Consumables, Lending, Historie)
kommen in den folgenden Phasen dazu.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # In Produktion managt Alembic das Schema, nicht die App selbst.
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.ENV}
