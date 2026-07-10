"""
Scandy-Lite - FastAPI-Einstiegspunkt.

Phase 2: Auth (lokal, cookie-basiert), Abteilungs-Scoping, Frontend-Fundament
(Design-System, responsive Nav, PWA-Shell). CRUD-Router für Items/Consumables/
Lending folgen in Phase 3/4.
"""
from contextlib import asynccontextmanager
import os

import logging

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings
from app.core.deps import Forbidden, RedirectToLogin
from app.core.templating import templates
from app.routers import admin_import, admin_settings, auth, consumables, history, items, pages, reservations, scan, workers

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


@app.middleware("http")
async def department_cookie_middleware(request: Request, call_next):
    """Setzt das Abteilungs-Auswahl-Cookie auf die tatsächlich ausgehende Antwort.

    Notwendig, weil unsere Routen fast durchweg eigene Response-Objekte
    zurückgeben (TemplateResponse/RedirectResponse) - FastAPIs eingebauter
    Mechanismus, Cookies über ein in eine Dependency injiziertes Response-
    Objekt zu setzen, funktioniert dann NICHT (das injizierte Objekt wird
    beim Zurückgeben verworfen). Middleware wirkt dagegen auf die Antwort,
    die tatsächlich rausgeht, unabhängig davon, wie der Endpunkt sie gebaut hat.
    Der Wert kommt aus get_current_department (app/core/deps.py), die ihn nur
    in request.state vormerkt statt selbst zu setzen.
    """
    response = await call_next(request)
    value = getattr(request.state, "department_cookie_value", None)
    if value is not None:
        from app.core.deps import DEPARTMENT_COOKIE_MAX_AGE, DEPARTMENT_COOKIE_NAME
        response.set_cookie(DEPARTMENT_COOKIE_NAME, value, max_age=DEPARTMENT_COOKIE_MAX_AGE, samesite="lax")
    return response

app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Eigener Mount für Uploads (Bilder) - bewusst getrennt von /static, weil
# /app/app/static im Image gebacken wird (Rebuild würde Uploads löschen),
# /app/uploads liegt dagegen auf einem eigenen, persistenten Docker-Volume.
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOADS_DIR), name="uploads")

app.include_router(auth.router)
app.include_router(pages.router)
app.include_router(scan.router)
app.include_router(reservations.router)
app.include_router(items.router)
app.include_router(consumables.router)
app.include_router(workers.router)
app.include_router(history.router)
app.include_router(admin_settings.router)
app.include_router(admin_import.router)


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
