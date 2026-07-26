"""
In-App-Update-Mechanismus für die native Proxmox-LXC-Installation (siehe
proxmox/install/scandy-lite-install.sh) - git pull + gefilterter pip install
+ alembic upgrade + Neustart der beiden systemd-Dienste.

NUR aktiv, wenn settings.NATIVE_LXC_DEPLOYMENT gesetzt ist (siehe
app/core/config.py) - bei Docker/Portainer gibt es weder systemd noch einen
git-Checkout im Container, dort läuft das Update über einen normalen
Portainer-Redeploy.

Sicherheitsnetz gegen unnötige Last (siehe Nutzer-Feedback: ein früherer,
zu häufig laufender git-fetch-Mechanismus hat spürbar CPU-/Netzwerklast
erzeugt): der Update-CHECK läuft NIE automatisch im Hintergrund, sondern nur
- wenn ein Admin explizit auf "Jetzt prüfen" klickt, oder
- beim Laden der Einstellungsseite, aber dann nur aus dem Cache (siehe
  get_cached_check) - ohne selbst zu fetchen.
Ein "Jetzt prüfen"-Klick fetcht höchstens einmal pro CHECK_CACHE_TTL
tatsächlich neu (siehe check_for_update(force=...)).
"""
import asyncio
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from app.models.common import utcnow

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK_FILE = REPO_ROOT / ".update.lock"
CHECK_CACHE_TTL = timedelta(hours=1)

# Dieselben Test-/Lint-only-Pakete wie proxmox/install/scandy-lite-install.sh
# - siehe Kommentar dort, warum httpx bewusst NICHT in dieser Liste steht.
_DEV_ONLY_PACKAGES = re.compile(r"^(pytest|pytest-asyncio|aiosqlite|ruff)==")


class UpdateStepError(Exception):
    """Ein einzelner Schritt (git/pip/alembic) ist fehlgeschlagen."""


@dataclass
class CheckResult:
    checked_at: datetime
    local_commit: str | None
    remote_commit: str | None
    update_available: bool
    error: str | None


@dataclass
class UpdateRunResult:
    success: bool
    log: str
    error: str | None = None


# Modul-weiter Cache (bewusst NICHT persistent/geteilt zwischen den beiden
# systemd-Diensten scandy-lite/scandy-lite-https - im schlimmsten Fall zeigt
# einer der beiden Prozesse kurz einen veralteten Cache-Stand, das ist für
# eine reine Anzeige unkritisch, siehe get_cached_check).
_last_check: CheckResult | None = None


async def _run(cmd: list[str], timeout: float, label: str = "") -> str:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=REPO_ROOT,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError as exc:
        proc.kill()
        raise UpdateStepError(f"{label or cmd[0]}: Zeitüberschreitung nach {timeout:.0f}s") from exc
    output = stdout.decode("utf-8", errors="replace")
    if proc.returncode != 0:
        raise UpdateStepError(f"{label or ' '.join(cmd)} fehlgeschlagen (Exit {proc.returncode}):\n{output[-2000:]}")
    return output


def get_cached_check() -> CheckResult | None:
    """Rein lesend, löst NIEMALS einen git fetch aus - für die Einstellungs-
    seite (kein Fetch bei jedem Seitenaufruf, siehe Modul-Docstring)."""
    return _last_check


async def check_for_update(force: bool = False) -> CheckResult:
    global _last_check
    now = utcnow()
    if not force and _last_check is not None and (now - _last_check.checked_at) < CHECK_CACHE_TTL:
        return _last_check

    try:
        await _run(["git", "fetch", "-q", "origin", "master"], timeout=30, label="git fetch")
        local = (await _run(["git", "rev-parse", "HEAD"], timeout=10, label="git rev-parse HEAD")).strip()
        remote = (await _run(["git", "rev-parse", "origin/master"], timeout=10, label="git rev-parse origin/master")).strip()
        result = CheckResult(
            checked_at=now, local_commit=local, remote_commit=remote,
            update_available=(local != remote), error=None,
        )
    except Exception as exc:  # noqa: BLE001 - jeder Fehler (Netzwerk, kein Git-Checkout, ...) soll nur angezeigt werden
        result = CheckResult(checked_at=now, local_commit=None, remote_commit=None, update_available=False, error=str(exc))

    _last_check = result
    return result


def _schedule_restart(delay_seconds: int = 2) -> None:
    """Feuert den Neustart beider Dienste leicht verzögert und komplett
    losgelöst vom aktuellen Prozess (start_new_session), damit die HTTP-
    Antwort dieses Requests noch beim Client ankommt, BEVOR der Prozess,
    der sie gerade ausliefert, durch den Neustart beendet wird."""
    subprocess.Popen(  # noqa: S603 - Kommando ist fest verdrahtet, keine Nutzereingabe beteiligt
        ["bash", "-c", f"sleep {delay_seconds} && systemctl restart scandy-lite scandy-lite-https"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


async def run_update() -> UpdateRunResult:
    """Führt das eigentliche Update aus: git reset --hard origin/master,
    gefilterter pip install (wie proxmox/install/scandy-lite-install.sh),
    alembic upgrade head, dann Dienst-Neustart. Schlägt ein Schritt fehl,
    wird NICHT neu gestartet - der alte Prozess läuft mit alten Modulen im
    Speicher weiter, der Dateistand auf der Platte kann aber vom laufenden
    Prozess abweichen, bis das manuell aufgeräumt wird (siehe zurückgegebene
    Fehlermeldung)."""
    if LOCK_FILE.exists():
        return UpdateRunResult(success=False, log="", error="Es läuft bereits ein Update (Sperrdatei vorhanden).")

    LOCK_FILE.write_text("")
    log_parts: list[str] = []
    try:
        log_parts.append(await _run(["git", "fetch", "-q", "origin", "master"], timeout=30, label="git fetch"))
        log_parts.append(await _run(["git", "reset", "-q", "--hard", "origin/master"], timeout=30, label="git reset"))

        requirements = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
        filtered = "\n".join(line for line in requirements.splitlines() if not _DEV_ONLY_PACKAGES.match(line))
        tmp_req = REPO_ROOT / "requirements-runtime.txt"
        tmp_req.write_text(filtered, encoding="utf-8")
        try:
            log_parts.append(await _run(
                [str(REPO_ROOT / "venv" / "bin" / "pip"), "install", "--prefer-binary", "-r", str(tmp_req)],
                timeout=300, label="pip install",
            ))
        finally:
            tmp_req.unlink(missing_ok=True)

        log_parts.append(await _run(
            [str(REPO_ROOT / "venv" / "bin" / "alembic"), "upgrade", "head"], timeout=120, label="alembic upgrade",
        ))
    except UpdateStepError as exc:
        return UpdateRunResult(success=False, log="\n".join(log_parts), error=str(exc))
    finally:
        LOCK_FILE.unlink(missing_ok=True)

    global _last_check
    _last_check = None  # naechster Check soll wieder frisch pruefen, nicht den veralteten Cache zeigen
    _schedule_restart()
    return UpdateRunResult(success=True, log="\n".join(log_parts), error=None)
