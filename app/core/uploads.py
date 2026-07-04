"""
Bild-Uploads für Gegenstände/Verbrauchsmaterial.

Bewusst einfach gehalten: jedes Bild wird nach Validierung IMMER als JPEG
gespeichert (ein Format, eine Dateiendung, keine Format-Zoo-Verwaltung),
EXIF-Rotation wird angewendet (sonst landen Handy-Fotos oft "falsch herum"),
und die längere Kante wird auf IMAGE_MAX_DIMENSION begrenzt - hält Dateien
klein und alle Karten im UI einheitlich handlich.

Dateiname = Entity-ID (z.B. "<item-id>.jpg") - macht Zuordnung trivial und
verhindert Namenskollisionen ohne zusätzliche Datenbank-Spalte für den Pfad.
"""
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from PIL import Image, ImageOps

from app.core.config import get_settings

settings = get_settings()


class InvalidImage(Exception):
    pass


def _uploads_root() -> Path:
    root = Path(settings.UPLOADS_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def image_path(subdir: str, entity_id: uuid.UUID) -> Path:
    return _uploads_root() / subdir / f"{entity_id}.jpg"


def image_url(subdir: str, entity_id: uuid.UUID) -> str:
    return f"/uploads/{subdir}/{entity_id}.jpg"


def has_image(subdir: str, entity_id: uuid.UUID) -> bool:
    return image_path(subdir, entity_id).exists()


async def save_image(file: UploadFile, subdir: str, entity_id: uuid.UUID) -> None:
    raw = await file.read()
    if len(raw) > settings.MAX_UPLOAD_BYTES:
        raise InvalidImage(f"Datei ist größer als {settings.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")

    try:
        img = Image.open(BytesIO(raw))
        img.verify()  # wirft bei kaputten/keinen echten Bilddaten
        img = Image.open(BytesIO(raw))  # nach verify() neu öffnen (verify() macht das Objekt unbrauchbar)
    except Exception as exc:  # Pillow wirft je nach Kaputtheit verschiedene Exception-Typen
        raise InvalidImage("Datei ist kein gültiges Bild.") from exc

    img = ImageOps.exif_transpose(img)  # Handy-Fotos: Rotation aus EXIF anwenden statt "falsch herum"
    if img.mode not in ("RGB",):
        img = img.convert("RGB")

    max_dim = settings.IMAGE_MAX_DIMENSION
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    target = image_path(subdir, entity_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(target, format="JPEG", quality=85, optimize=True)


def delete_image(subdir: str, entity_id: uuid.UUID) -> None:
    path = image_path(subdir, entity_id)
    if path.exists():
        path.unlink()
