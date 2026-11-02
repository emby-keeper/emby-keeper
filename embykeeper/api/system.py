import os
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException

from .auth import require_auth
from ..schema import Config
from ..config import config as config_manager

router = APIRouter()


def _count_accounts(cfg: Config) -> Dict[str, int]:
    tg = len(cfg.telegram.account or []) if cfg.telegram and cfg.telegram.account else 0
    em = len(cfg.emby.account or []) if cfg.emby and cfg.emby.account else 0
    return {"telegram": tg, "emby": em}


def _module_summary(cfg: Config) -> Dict[str, int]:
    telegram_accounts = cfg.telegram.account if cfg.telegram and cfg.telegram.account else []
    emby_accounts = cfg.emby.account if cfg.emby and cfg.emby.account else []
    subsonic_accounts = cfg.subsonic.account if cfg.subsonic and cfg.subsonic.account else []

    return {
        "checkiner_accounts": sum(
            1 for account in telegram_accounts if account.enabled and account.checkiner
        ),
        "monitor_accounts": sum(1 for account in telegram_accounts if account.enabled and account.monitor),
        "messager_accounts": sum(1 for account in telegram_accounts if account.enabled and account.messager),
        "registrar_accounts": sum(
            1 for account in telegram_accounts if account.enabled and account.registrar
        ),
        "emby_accounts": sum(1 for account in emby_accounts if account.enabled),
        "subsonic_accounts": sum(1 for account in subsonic_accounts if account.enabled),
    }


@router.get("/system/status")
async def status(_: bool = Depends(require_auth)):
    try:
        from ..runinfo import RunContext, RunStatus
        from ..cache import cache
        from .config import _read_config_dict

        cfg = Config(**_read_config_dict())
        counts = _count_accounts(cfg)

        running = []
        keys = cache.find_by_prefix("runinfo.")
        for key in keys:
            if key.startswith("runinfo.children."):
                continue
            rid = key.replace("runinfo.", "")
            ctx = RunContext.get(rid)
            if ctx and ctx.status in [RunStatus.PENDING, RunStatus.INITIALIZING, RunStatus.RUNNING]:
                running.append(rid)

        return {
            "counts": counts,
            "modules": _module_summary(cfg),
            "running": running,
            "pid": os.getpid(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {e}")


@router.post("/system/stop")
async def stop(_: bool = Depends(require_auth)):
    raise HTTPException(
        status_code=410,
        detail="Business process lifecycle is managed by /api/pm/* on the panel API.",
    )


@router.post("/system/restart")
async def restart(_: bool = Depends(require_auth)):
    raise HTTPException(
        status_code=410,
        detail="Business process lifecycle is managed by /api/pm/* on the panel API.",
    )
