"""
SMTP-Konto für System-Mails (Willkommens-/Passwort-Reset-Mails, Mindest-
bestand-Benachrichtigungen) - Konfiguration + Testversand.
"""
from fastapi import APIRouter, Depends, Form
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.crypto import encrypt_secret
from app.core.database import get_session
from app.core.deps import populate_nav_context, require_admin, verify_csrf
from app.core.email import get_email_settings, send_email
from app.core.responses import redirect_with_query
from app.core.templating import templates
from app.models.email_settings import EmailSettings
from app.models.user import User

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


@router.post("/email-settings")
async def update_email_settings(
    smtp_host: str = Form(...),
    smtp_port: int = Form(587),
    smtp_username: str = Form(""),
    smtp_password: str = Form(""),
    use_tls: str = Form(""),
    from_address: str = Form(...),
    from_name: str = Form("Scandy-Lite"),
    enabled: str = Form(""),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    existing = await get_email_settings(session)
    if not existing:
        existing = EmailSettings(smtp_host=smtp_host, from_address=from_address)
        session.add(existing)

    existing.smtp_host = smtp_host.strip()
    existing.smtp_port = smtp_port
    existing.smtp_username = smtp_username.strip() or None
    if smtp_password:
        # Leer gelassen = vorhandenes Passwort behalten - wird nie im
        # Klartext zurück ins Formular gerendert, ein leeres Feld darf das
        # gespeicherte Passwort also nicht versehentlich löschen.
        existing.smtp_password_encrypted = encrypt_secret(smtp_password)
    existing.use_tls = bool(use_tls)
    existing.from_address = from_address.strip()
    existing.from_name = from_name.strip() or "Scandy-Lite"
    existing.enabled = bool(enabled)

    session.add(existing)
    await session.commit()
    return redirect_with_query("/admin/settings", fragment="email", ok="E-Mail-Einstellungen gespeichert.")


@router.post("/email-settings/test")
async def test_email_settings(
    test_to: str = Form(...),
    user: User = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
):
    html_body = templates.get_template("email/password_reset.html").render(
        username=None, reset_url="https://example.invalid/nur-ein-test"
    )
    sent = await send_email(session, test_to.strip(), "Scandy-Lite: Test-Mail", html_body)
    if sent:
        return redirect_with_query("/admin/settings", fragment="email", ok=f"Test-Mail an {test_to} verschickt.")
    return redirect_with_query(
        "/admin/settings", fragment="email",
        error="Test-Mail konnte nicht verschickt werden - Zugangsdaten/Einstellungen prüfen (Details im Server-Log).",
    )
