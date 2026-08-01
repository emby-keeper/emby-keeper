import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
import tomli as tomllib
import tomlkit
from pydantic import BaseModel, ValidationError

from .auth import require_auth
from .runinfo import _sort_datetime
from ..schema import Config, TelegramAccount, TelegramConfig, format_errors
from ..config import config as config_manager
from ..runinfo import RunContext, RunStatus


router = APIRouter()


class TelegramAccountPayload(BaseModel):
    phone: str
    enabled: bool = True
    checkiner: bool = True
    monitor: bool = False
    messager: bool = False
    registrar: bool = False
    api_id: Optional[str] = None
    api_hash: Optional[str] = None
    session: Optional[str] = None


class TelegramSettingsPayload(BaseModel):
    checkiner_enabled: bool = True
    monitor_enabled: bool = True
    messager_enabled: bool = True
    registrar_enabled: bool = True


def _active_config_file():
    conf_file = getattr(config_manager, "_conf_file", None)
    if conf_file:
        return Path(conf_file)
    return config_manager.basedir / "config.toml"


def _config_path():
    return _active_config_file()


def _read_config_dict() -> Dict[str, Any]:
    cfg_path = _config_path()
    if not cfg_path.exists():
        return {}
    with open(cfg_path, "rb") as file:
        return tomllib.load(file)


def _write_config_dict(cfg: Dict[str, Any]):
    cfg_path = _config_path()
    with open(cfg_path, "w", encoding="utf-8") as file:
        file.write(tomlkit.dumps(cfg))
    # 写盘后强制同步 config_manager 内存（watchdog awatch 不总是触发 reload）
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(config_manager.reload_conf(_active_config_file()))
    except RuntimeError:
        pass


def _load_config() -> Config:
    cfg_path = _active_config_file()
    return Config(**(tomllib.loads(cfg_path.read_text()) if cfg_path.exists() else {}))


def _serialize_account(account: TelegramAccount) -> Dict[str, Any]:
    last_checkin_status, last_checkin_time = _get_last_checkin_status(account.phone)
    return {
        "phone": account.phone,
        "masked_phone": TelegramAccount.get_phone_masked(account.phone),
        "enabled": bool(account.enabled),
        "checkiner": bool(account.checkiner),
        "monitor": bool(account.monitor),
        "messager": bool(account.messager),
        "registrar": bool(account.registrar),
        "api_id": account.api_id,
        "api_hash": account.api_hash,
        "session": account.session,
        "site_override": bool(account.site),
        "checkiner_config_override": bool(account.checkiner_config),
        "registrar_config_override": bool(account.registrar_config),
        "last_checkin_status": last_checkin_status,
        "last_checkin_time": last_checkin_time,
    }


def _get_last_checkin_status(phone: str) -> Tuple[Optional[str], Optional[str]]:
    latest_status: Optional[str] = None
    latest_time: Optional[datetime] = None
    target_description = f"{phone} 账号签到"

    contexts = [ctx for ctx in RunContext.list_all() if ctx.description == target_description]

    for ctx in contexts:
        if ctx.status in {RunStatus.PENDING, RunStatus.INITIALIZING, RunStatus.RUNNING, RunStatus.CATAGORY}:
            continue

        status = _infer_checkin_outcome(ctx)
        if not status:
            continue

        run_time = _sort_datetime(ctx.end_time or ctx.start_time)
        if latest_time is None or run_time > latest_time:
            latest_status = status
            latest_time = run_time

    return latest_status, latest_time.isoformat() if latest_time and latest_time != _sort_datetime(None) else None


def _infer_checkin_outcome(ctx: RunContext) -> Optional[str]:
    """Infer account-level checkin outcome from status_info, status, or logs."""
    if ctx.status_info == "签到部分失败":
        return "partial_failed"
    if ctx.status_info == "签到失败" or ctx.status in {RunStatus.FAIL, RunStatus.ERROR, RunStatus.CANCELLED}:
        return "failed"
    if ctx.status_info == "签到成功" or ctx.status == RunStatus.SUCCESS:
        return "success"

    for log in reversed(list(ctx.yield_logs(include_children=False))):
        message = str(log.message or "")
        if "签到部分失败" in message:
            return "partial_failed"
        if "签到失败" in message:
            return "failed"
        if "签到成功" in message:
            return "success"
    return None



def _replace_accounts(raw: Dict[str, Any], accounts: List[TelegramAccount]) -> Dict[str, Any]:
    merged = dict(raw)
    telegram_section = dict(merged.get("telegram") or {})
    telegram_section["account"] = [account.model_dump(exclude_none=True) for account in accounts]
    if "use_proxy" not in telegram_section:
        telegram_section["use_proxy"] = True
    merged["telegram"] = telegram_section
    return merged


def _load_telegram_accounts() -> Tuple[Config, Dict[str, Any], List[TelegramAccount]]:
    raw = _read_config_dict()
    model = Config(**raw)
    accounts = list(model.telegram.account if model.telegram and model.telegram.account else [])
    return model, raw, accounts


@router.get("/telegram/accounts")
async def list_telegram_accounts(_: bool = Depends(require_auth)):
    try:
        cfg = _load_config()
        accounts = cfg.telegram.account if cfg.telegram and cfg.telegram.account else []
        items: List[Dict] = []
        summary = {
            "total": len(accounts),
            "enabled": 0,
            "checkiner": 0,
            "monitor": 0,
            "messager": 0,
            "registrar": 0,
            "use_proxy": bool(cfg.telegram.use_proxy) if cfg.telegram else True,
            "checkiner_enabled": bool(cfg.checkiner.enabled) if cfg.checkiner and cfg.checkiner.enabled is not None else True,
            "monitor_enabled": bool(cfg.monitor.enabled) if cfg.monitor and cfg.monitor.enabled is not None else True,
            "messager_enabled": bool(cfg.messager.enabled) if cfg.messager and cfg.messager.enabled is not None else True,
            "registrar_enabled": bool(cfg.registrar.enabled) if cfg.registrar and cfg.registrar.enabled is not None else True,
        }
        for a in accounts:
            status = _serialize_account(a)
            items.append(status)
            if status["enabled"]:
                summary["enabled"] += 1
            if status["checkiner"]:
                summary["checkiner"] += 1
            if status["monitor"]:
                summary["monitor"] += 1
            if status["messager"]:
                summary["messager"] += 1
            if status["registrar"]:
                summary["registrar"] += 1
        return {"accounts": items, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list telegram accounts: {e}")


@router.post("/telegram/settings")
async def save_telegram_settings(payload: TelegramSettingsPayload, _: bool = Depends(require_auth)):
    try:
        raw = _read_config_dict()
        merged = dict(raw)

        checkiner_section = dict(merged.get("checkiner") or {})
        checkiner_section["enabled"] = payload.checkiner_enabled
        merged["checkiner"] = checkiner_section

        monitor_section = dict(merged.get("monitor") or {})
        monitor_section["enabled"] = payload.monitor_enabled
        merged["monitor"] = monitor_section

        messager_section = dict(merged.get("messager") or {})
        messager_section["enabled"] = payload.messager_enabled
        merged["messager"] = messager_section

        registrar_section = dict(merged.get("registrar") or {})
        registrar_section["enabled"] = payload.registrar_enabled
        merged["registrar"] = registrar_section

        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode='json', exclude_none=True, exclude_unset=True))
        return {"success": True}
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save telegram settings: {e}")


@router.get("/telegram/accounts/{phone}")
async def get_telegram_account(phone: str, _: bool = Depends(require_auth)):
    try:
        cfg = _load_config()
        accounts = cfg.telegram.account if cfg.telegram and cfg.telegram.account else []
        for account in accounts:
            if account.phone == phone:
                return {"account": _serialize_account(account)}
        raise HTTPException(status_code=404, detail="Telegram account not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load telegram account: {e}")


@router.post("/telegram/accounts")
async def create_telegram_account(payload: TelegramAccountPayload, _: bool = Depends(require_auth)):
    try:
        _, raw, accounts = _load_telegram_accounts()
        account = TelegramAccount(**payload.model_dump(exclude_none=True))

        if any(existing.phone == account.phone for existing in accounts):
            raise HTTPException(status_code=409, detail="Telegram account already exists")

        accounts.append(account)
        merged = _replace_accounts(raw, accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode='json', exclude_none=True, exclude_unset=True))
        return {"success": True, "account": _serialize_account(account)}
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create telegram account: {e}")


@router.put("/telegram/accounts/{phone}")
async def update_telegram_account(phone: str, payload: TelegramAccountPayload, _: bool = Depends(require_auth)):
    try:
        _, raw, accounts = _load_telegram_accounts()
        next_account = TelegramAccount(**payload.model_dump(exclude_none=True))
        updated = False
        next_accounts: List[TelegramAccount] = []

        for account in accounts:
            if account.phone == phone:
                next_accounts.append(next_account)
                updated = True
            else:
                next_accounts.append(account)

        if not updated:
            raise HTTPException(status_code=404, detail="Telegram account not found")

        if sum(1 for account in next_accounts if account.phone == next_account.phone) > 1:
            raise HTTPException(status_code=409, detail="Telegram account phone already exists")

        merged = _replace_accounts(raw, next_accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode='json', exclude_none=True, exclude_unset=True))
        return {"success": True, "account": _serialize_account(next_account)}
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update telegram account: {e}")


@router.delete("/telegram/accounts/{phone}")
async def delete_telegram_account(phone: str, _: bool = Depends(require_auth)):
    try:
        model, raw, accounts = _load_telegram_accounts()
        next_accounts = [account for account in accounts if account.phone != phone]

        if len(next_accounts) == len(accounts):
            raise HTTPException(status_code=404, detail="Telegram account not found")

        merged = _replace_accounts(raw, next_accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode='json', exclude_none=True, exclude_unset=True))
        return {
            "success": True,
            "summary": {
                "total": len(next_accounts),
                "use_proxy": bool(model.telegram.use_proxy) if model.telegram else True,
            },
        }
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete telegram account: {e}")
