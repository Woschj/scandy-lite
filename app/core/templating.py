"""Zentrale Jinja2Templates-Instanz, damit alle Router dieselbe Konfiguration nutzen."""
from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.core.uploads import has_image, image_url

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


templates = Jinja2Templates(
    directory=str(TEMPLATES_DIR),
    context_processors=[_inject_nav_context],
)
templates.env.globals["has_image"] = has_image
templates.env.globals["image_url"] = image_url
