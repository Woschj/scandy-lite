"""
Eingebauter Scandy2-Import: Admins können ein Scandy2-Backup-ZIP (oder die
darin enthaltene JSON-Datei) direkt in der Weboberfläche hochladen, statt
das Migrationsskript über die Kommandozeile auszuführen.

Wiederverwendet dieselbe, bereits ausführlich getestete Logik wie das CLI-
Skript (migrations_legacy/migrate_core.py) - hier nur eine dünne Web-Schicht
darüber. migrate_core arbeitet mit einer SYNCHRONEN SQLModel-Session (war für
ein CLI-Skript gebaut); da unsere Web-App durchgehend async ist, läuft der
eigentliche Import-Vorgang in einem Thread (asyncio.to_thread), damit er den
Event-Loop nicht blockiert.
"""
import asyncio
import sys
from pathlib import Path

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlmodel import Session, create_engine

from app.core.config import get_settings
from app.core.deps import require_admin, populate_switchable_departments
from app.core.scandy2_import import ImportParseError, parse_scandy2_export
from app.core.templating import templates
from app.models.user import User

# migrations_legacy liegt außerhalb des app/-Pakets (Projekt-Root) - Pfad
# ergänzen, damit der Import unabhängig vom Arbeitsverzeichnis funktioniert.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from migrations_legacy.migrate_core import migrate  # noqa: E402

router = APIRouter(prefix="/admin/import", tags=["admin-import"], dependencies=[Depends(populate_switchable_departments)])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB - Backup-JSON ohne Medien ist üblicherweise klein


def _run_migration_sync(data: dict, apply: bool) -> dict:
    """Läuft in einem Thread (siehe asyncio.to_thread-Aufrufe unten) - eigene,
    kurzlebige synchrone Engine/Session, komplett unabhängig von der
    App-weiten async Engine."""
    settings = get_settings()
    engine = create_engine(settings.DATABASE_URL_SYNC)
    with Session(engine) as session:
        result = migrate(session, data, apply=apply)
    engine.dispose()
    return result


@router.get("")
async def import_form(
    request: Request,
    user: User = Depends(require_admin),
):
    return templates.TemplateResponse(
        request, "admin/import.html",
        {"user": user, "result": None, "mode": None, "error": None},
    )


@router.post("/preview")
async def import_preview(
    request: Request,
    file: UploadFile,
    user: User = Depends(require_admin),
):
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        return templates.TemplateResponse(
            request, "admin/import.html",
            {"user": user, "result": None, "mode": None, "error": "Datei ist zu groß (max. 50 MB)."},
            status_code=413,
        )

    try:
        data = parse_scandy2_export(file.filename or "", raw)
    except ImportParseError as exc:
        return templates.TemplateResponse(
            request, "admin/import.html",
            {"user": user, "result": None, "mode": None, "error": str(exc)},
            status_code=400,
        )

    result = await asyncio.to_thread(_run_migration_sync, data, False)
    return templates.TemplateResponse(
        request, "admin/import.html",
        {"user": user, "result": result, "mode": "preview", "error": None, "filename": file.filename},
    )


@router.post("/apply")
async def import_apply(
    request: Request,
    file: UploadFile,
    user: User = Depends(require_admin),
):
    raw = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(raw) > MAX_UPLOAD_BYTES:
        return templates.TemplateResponse(
            request, "admin/import.html",
            {"user": user, "result": None, "mode": None, "error": "Datei ist zu groß (max. 50 MB)."},
            status_code=413,
        )

    try:
        data = parse_scandy2_export(file.filename or "", raw)
    except ImportParseError as exc:
        return templates.TemplateResponse(
            request, "admin/import.html",
            {"user": user, "result": None, "mode": None, "error": str(exc)},
            status_code=400,
        )

    result = await asyncio.to_thread(_run_migration_sync, data, True)
    return templates.TemplateResponse(
        request, "admin/import.html",
        {"user": user, "result": result, "mode": "applied", "error": None, "filename": file.filename},
    )
