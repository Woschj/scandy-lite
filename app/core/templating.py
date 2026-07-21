"""Zentrale Jinja2Templates-Instanz, damit alle Router dieselbe Konfiguration nutzen."""
import json
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.core.config import get_settings
from app.core.security import generate_csrf_token
from app.core.uploads import has_image, image_url
from app.version import __version__

settings = get_settings()

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"


def _inject_nav_context(request: Request) -> dict:
    """Macht has_any_staff_role (Nav-Sichtbarkeit von Scannen/Mitarbeiter/
    Historie) bei JEDEM Template-Rendering automatisch verfügbar, unabhängig
    davon, ob der jeweilige Router es explizit in den Kontext gepackt hat.

    Bewusst NUR ein synchrones Auslesen aus request.state - die eigentliche
    (async) DB-Abfrage passiert vorher in der populate_nav_context-Dependency
    (app/core/deps.py), die jeder Seiten-Router einbindet. Ein Context-
    Processor kann selbst keine async-Arbeit machen (Event-Loop läuft hier
    schon), deshalb die Aufteilung in zwei Schritte.
    """
    return {"has_any_staff_role": getattr(request.state, "has_any_staff_role", False)}


def csrf_token(request: Request) -> str:
    """Für `{{ csrf_token(request) }}` in Formularen - leitet das Token aus
    dem aktuellen Session-Cookie ab (siehe app.core.security). Vor dem Login
    gibt es kein Session-Cookie; dann liefert das einen "leeren" Token, was
    unkritisch ist, da CSRF-geschützte Router den auth-Router nicht
    einschließen (siehe app.core.deps.verify_csrf)."""
    return generate_csrf_token(request.cookies.get(settings.SESSION_COOKIE_NAME, ""))


templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
    context_processors=[_inject_nav_context],
)
templates.env.globals["has_image"] = has_image
templates.env.globals["image_url"] = image_url
templates.env.globals["csrf_token"] = csrf_token
# Cache-Busting für CSS/JS: StaticFiles sendet kein Cache-Control, Browser
# dürfen Assets deshalb heuristisch (Last-Modified-basiert) wiederverwenden -
# nach einem Deploy kann so veraltetes CSS/JS aktiv bleiben, sogar durch den
# network-first Service Worker hindurch (dessen fetch() nutzt denselben
# HTTP-Cache). Eine versionierte URL (?v=...) ändert sich mit jedem Release
# und erzwingt damit garantiert einen frischen Abruf.
templates.env.globals["asset_version"] = __version__
# `tojson` ist eine Flask-Eigenheit, kein Jinja2-Kernfilter - wird hier für
# Alpine.js-`x-data`-Attribute gebraucht (JSON aus Python-Werten in HTML-
# Attribute einbetten, siehe items/form.html). Bewusst KEIN Markup/safe-
# Wrapping: das automatische HTML-Escaping der Templates (aktiv für .html-
# Dateien) escaped z.B. Anführungszeichen zu &quot; - das ist innerhalb eines
# doppelt gequoteten Attributs korrekt und sicher, der Browser dekodiert es
# beim Parsen des Attributwerts wieder zurück.
templates.env.filters["tojson"] = json.dumps
