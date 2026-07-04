"""Zentrale Jinja2Templates-Instanz, damit alle Router dieselbe Konfiguration nutzen."""
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.core.uploads import has_image, image_url

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.globals["has_image"] = has_image
templates.env.globals["image_url"] = image_url
