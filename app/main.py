"""
Scandy-Lite - FastAPI-Einstiegspunkt.

Phase 2: Auth (lokal, cookie-basiert), Abteilungs-Scoping, Frontend-Fundament
(Design-System, responsive Nav, PWA-Shell). CRUD-Router für Items/Consumables/
Lending folgen in Phase 3/4.
"""
from contextlib import asynccontextmanager

import logging

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.deps import Forbidden, RedirectToLogin
from app.core.templating import templates
from app.routers import admin_settings, auth, consumables, items, pages, scan, workers

settings = get_settings()
logger = logging.getLogger("scandy-lite")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.ENV == "production" and settings.SECRET_KEY == "change-me-in-production":
        logger.warning(
            "SECRET_KEY steht noch auf dem Default-Wert! Login-Sessions sind damit fälschbar. "
            "Bitte in der Portainer-Stack-Konfiguration SECRET_KEY setzen (z.B. mit `openssl rand -hex 32`)."
        )
    # In Produktion managt Alembic das Schema, nicht die App selbst.
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(scan.router)
app.include_router(items.router)
app.include_router(consumables.router)
app.include_router(workers.router)
app.include_router(admin_settings.router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse(url="/static/icons/icon.svg")


@app.exception_handler(RedirectToLogin)
async def handle_redirect_to_login(request: Request, exc: RedirectToLogin):
    return RedirectResponse(url="/auth/login", status_code=303)


@app.exception_handler(Forbidden)
async def handle_forbidden(request: Request, exc: Forbidden):
    return templates.TemplateResponse(request, "errors/403.html", {}, status_code=403)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "env": settings.ENV}
