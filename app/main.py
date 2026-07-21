"""
Scandy-Lite - FastAPI-Einstiegspunkt.

Phase 2: Auth (lokal, cookie-basiert), Abteilungs-Scoping, Frontend-Fundament
(Design-System, responsive Nav, PWA-Shell). CRUD-Router für Items/Consumables/
Lending folgen in Phase 3/4.
"""
from contextlib import asynccontextmanager
import asyncio
import os
import socket
import sys

import logging

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import get_settings
from app.core.database import engine
from app.core.deps import Forbidden, RedirectToLogin
from app.core.low_stock import low_stock_check_loop
from app.core.static_cache import CachedStaticFiles
from app.core.templating import templates
from app.routers import admin_import, admin_settings, auth, badge, consumables, history, items, oidc, pages, pickup, reservations, scan

settings = get_settings()

logging.basicConfig(
    level=logging.DEBUG if settings.ENV == "development" else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("scandy-lite")

# Name des Caddy-Reverse-Proxy-Containers in docker-compose.yml. Uvicorn läuft
# ohne --proxy-headers: request.client.host wäre für JEDEN über Caddy
# laufenden Request (zwingend für Kamera-Scan, siehe INSTALL.md) sonst die
# interne Docker-IP des Caddy-Containers, nicht die echte Client-IP - macht
# das IP-basierte Rate-Limiting in auth.py wirkungslos (ein Nutzer mit
# Tippfehlern sperrt versehentlich ALLE HTTPS-Nutzer). Einmal beim Start
# aufgelöst statt pro Request (Docker-DNS-Lookups sind zwar schnell, aber
# synchron/blockierend - unnötig auf dem Hot Path).
_TRUSTED_PROXY_HOSTNAME = "caddy"
_trusted_proxy_ips: set[str] = set()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _trusted_proxy_ips
    try:
        _trusted_proxy_ips = {info[4][0] for info in socket.getaddrinfo(_TRUSTED_PROXY_HOSTNAME, None)}
    except socket.gaierror:
        # Caddy-Service nicht im Compose-Stack (siehe Kommentar dort: "bei
        # Nichtgebrauch einfach entfernen") - dann gibt es auch keinen
        # Reverse-Proxy, dessen Header vertraut werden müsste.
        _trusted_proxy_ips = set()

    # Läuft dauerhaft im Hintergrund neben den Request-Handlern (siehe
    # app/core/low_stock.py) - kein externer Cron/Scheduler-Dienst nötig.
    low_stock_task = asyncio.create_task(low_stock_check_loop())

    yield

    low_stock_task.cancel()
    try:
        await low_stock_task
    except asyncio.CancelledError:
        pass
    await engine.dispose()


app = FastAPI(
    title=settings.APP_NAME,
    version="0.1.0",
    lifespan=lifespan,
)


@app.middleware("http")
async def trust_forwarded_for_from_caddy(request: Request, call_next):
    """Ersetzt request.client.host durch die per X-Forwarded-For gemeldete
    echte Client-IP - aber NUR, wenn die Verbindung tatsächlich vom
    Caddy-Container kommt (siehe _trusted_proxy_ips oben). Ein Client, der
    APP_PORT direkt anspricht (am Proxy vorbei), kann sich nicht als "caddy"
    ausgeben - Docker bestimmt die Peer-IP über die echte TCP-Verbindung,
    nicht über selbst gesetzte Header. Ohne diesen Check würde ein beliebiger
    direkter Client per X-Forwarded-For das Rate-Limiting in auth.py umgehen/
    fälschen können."""
    client = request.client
    if client and client.host in _trusted_proxy_ips:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            real_ip = forwarded_for.split(",")[0].strip()
            if real_ip:
                request.scope["client"] = (real_ip, client.port)
    return await call_next(request)


if settings.oidc_enabled:
    # Nur fuer den kurzlebigen state/nonce WAEHREND des OIDC-Handshakes
    # (app/routers/oidc.py) - eigener, von unserem eigentlichen Session-
    # Cookie (SESSION_COOKIE_NAME) getrennter, signierter Cookie. Nicht
    # registriert, wenn SSO gar nicht konfiguriert ist (kein unnoetiger
    # Cookie fuer Installationen ohne dieses Feature).
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SECRET_KEY,
        session_cookie="scandy_oidc_state",
        https_only=settings.SESSION_COOKIE_SECURE,
        same_site="lax",
    )

# CSS/JS werden seit der Cache-Busting-Umstellung immer mit ?v=<Version>
# referenziert - eine SOLCHE Anfrage darf ein Jahr lang unrevalidiert aus dem
# Browser-Cache bedient werden (ändert sich der Inhalt, ändert sich die URL).
# Unversionierte Treffer (Manifest, Icons - ändern sich praktisch nie, tragen
# aber kein ?v=) bekommen nur eine kurze, revalidierende Cache-Dauer.
app.mount(
    "/static",
    CachedStaticFiles(directory="app/static", cache_control="public, max-age=3600", versioned_cache_control="public, max-age=31536000, immutable"),
    name="static",
)

# Eigener Mount für Uploads (Bilder) - bewusst getrennt von /static, weil
# /app/app/static im Image gebacken wird (Rebuild würde Uploads löschen),
# /app/uploads liegt dagegen auf einem eigenen, persistenten Docker-Volume.
# Bilder werden NICHT versioniert referenziert (dieselbe URL bei Ersatz-
# Upload) - deshalb nur kurze Cache-Dauer mit Revalidierung (ETag/
# Last-Modified liefert StaticFiles ohnehin automatisch), keine "immutable".
os.makedirs(settings.UPLOADS_DIR, exist_ok=True)
app.mount(
    "/uploads",
    CachedStaticFiles(directory=settings.UPLOADS_DIR, cache_control="public, max-age=300, must-revalidate"),
    name="uploads",
)

app.include_router(auth.router)
app.include_router(oidc.router)
app.include_router(pages.router)
app.include_router(badge.router)
app.include_router(scan.router)
app.include_router(pickup.router)
app.include_router(reservations.router)
app.include_router(items.router)
app.include_router(consumables.router)
app.include_router(history.router)
app.include_router(admin_settings.router)
app.include_router(admin_import.router)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return RedirectResponse(url="/static/icons/icon.svg")


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    # Bewusst NICHT unter /static/ (StaticFiles-Mount) ausgeliefert: ein
    # Service Worker kontrolliert per Default nur den Pfad, unter dem er
    # liegt - unter /static/sw.js gecacht, würde er nie die eigentlichen
    # App-Seiten (/scan, /items, ...) sehen. Cache-Control: no-cache, damit
    # Browser bei jedem Start auf eine neue Version prüfen (Service Worker
    # werden sonst bis zu 24h lang aus dem HTTP-Cache bedient).
    return FileResponse(
        "app/static/sw.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.exception_handler(RedirectToLogin)
async def handle_redirect_to_login(request: Request, exc: RedirectToLogin):
    return RedirectResponse(url="/auth/login", status_code=303)


@app.exception_handler(Forbidden)
async def handle_forbidden(request: Request, exc: Forbidden):
    return templates.TemplateResponse(request, "errors/403.html", {}, status_code=403)


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception):
    logger.error("Unerwarteter Fehler bei %s %s", request.method, request.url.path, exc_info=True)
    return templates.TemplateResponse(request, "errors/500.html", {}, status_code=500)


@app.get("/health")
async def health():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        logger.error("Healthcheck: Datenbank nicht erreichbar", exc_info=True)
        return JSONResponse({"status": "error"}, status_code=503)
    return {"status": "ok", "env": settings.ENV}
