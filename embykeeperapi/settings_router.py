from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .auth import require_auth
from .pm import pm
from .settings import PanelSettings, panel_settings

router = APIRouter()


class PanelSettingsPayload(BaseModel):
    backend_config_file: str = Field(
        default="", description="Business config file. Empty means <basedir>/config.toml."
    )


def _validate_and_prepare(payload: PanelSettingsPayload) -> PanelSettings:
    current = panel_settings.get()
    settings = PanelSettings(
        backend_basedir=current.backend_basedir,
        backend_config_file=payload.backend_config_file,
    )

    try:
        basedir = panel_settings.resolved_backend_basedir()
        if settings.backend_config_file.strip():
            config_file = Path(settings.backend_config_file).expanduser().resolve()
        else:
            config_file = basedir / "config.toml"
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"路径无效: {exc}") from exc

    if settings.backend_config_file.strip() and config_file.exists() and not config_file.is_file():
        raise HTTPException(status_code=400, detail="配置路径已存在，但不是文件")

    return settings


@router.get("/settings/panel")
async def get_panel_settings(_: bool = Depends(require_auth)):
    panel_settings.reload()
    view = panel_settings.public_view()
    view["backend"] = pm.status()
    return view


@router.post("/settings/panel")
async def save_panel_settings(payload: PanelSettingsPayload, _: bool = Depends(require_auth)):
    settings = _validate_and_prepare(payload)
    panel_settings.save(settings)

    restarted = False
    restart_error: Optional[str] = None
    try:
        if pm.owns_backend() or pm.is_running():
            pm.restart()
            ready = await pm.wait_until_ready()
            if not ready:
                restart_error = pm.status().get("last_error") or "业务进程重启超时"
            else:
                restarted = True
    except Exception as exc:
        restart_error = str(exc)

    view = panel_settings.public_view()
    view["success"] = restart_error is None
    view["restarted"] = restarted
    view["backend"] = pm.status()
    if restart_error:
        view["restart_error"] = restart_error
        raise HTTPException(status_code=500, detail=view)
    return view
