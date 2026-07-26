"""
Routen für den In-App-Update-Mechanismus - nur für die native Proxmox-LXC-
Installation (siehe app/core/self_update.py + config.py::NATIVE_LXC_DEPLOYMENT).
Bei Docker/Portainer bleibt das Flag False, beide Routen antworten dann mit
403 statt irgendetwas auszuführen.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.core.config import get_settings
from app.core.deps import Forbidden, populate_nav_context, require_admin, verify_csrf
from app.core.self_update import check_for_update, run_update
from app.core.templating import templates
from app.models.user import User

router = APIRouter(prefix="/admin/update", tags=["admin-update"], dependencies=[Depends(populate_nav_context), Depends(verify_csrf)])


def _require_native_lxc() -> None:
    if not get_settings().NATIVE_LXC_DEPLOYMENT:
        raise Forbidden()


@router.post("/check")
async def trigger_check(user: User = Depends(require_admin)):
    _require_native_lxc()
    await check_for_update(force=True)
    return RedirectResponse("/admin/settings#update", status_code=303)


@router.post("/run")
async def trigger_run(request: Request, user: User = Depends(require_admin)):
    _require_native_lxc()
    result = await run_update()
    return templates.TemplateResponse(request, "admin/update_result.html", {"user": user, "result": result})
