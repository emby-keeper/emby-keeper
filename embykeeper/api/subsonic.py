import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
import tomli as tomllib
import tomlkit
from pydantic import BaseModel, Field, ValidationError

from .auth import require_auth
from ..cache import cache
from ..config import config as config_manager
from ..schema import Config, SubsonicAccount, format_errors


router = APIRouter()

SUBSONIC_ACCOUNT_HISTORY_LIMIT = 30


class SubsonicAccountPayload(BaseModel):
    url: str
    username: str
    password: str = ''
    name: Optional[str] = None
    enabled: bool = True
    use_proxy: bool = True
    time: List[int] = Field(default_factory=lambda: [300, 600])
    interval_days: Optional[str] = None
    time_range: Optional[str] = None


class SubsonicSettingsPayload(BaseModel):
    enabled: bool = True


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


def _account_history_cache_key(account: SubsonicAccount) -> str:
    return f"subsonic.account_history.{account.url.host}.{account.username}"


def _read_account_history(account: SubsonicAccount) -> List[Dict[str, str]]:
    raw = cache.get(_account_history_cache_key(account), []) or []
    records: List[Dict[str, str]] = []
    if not isinstance(raw, list):
        return records
    for item in raw:
        if not isinstance(item, dict):
            continue
        status = item.get("status")
        time_value = item.get("time")
        if status not in {"success", "failed"} or not isinstance(time_value, str):
            continue
        records.append({"status": status, "time": time_value})
    records.sort(key=lambda item: item["time"], reverse=True)
    return records[:SUBSONIC_ACCOUNT_HISTORY_LIMIT]


def _serialize_account(account: SubsonicAccount) -> Dict[str, Any]:
    watch_history = _read_account_history(account)
    return {
        "id": _account_key(account),
        "url": str(account.url),
        "username": account.username,
        "name": account.name,
        "enabled": bool(account.enabled),
        "use_proxy": bool(account.use_proxy),
        "time": account.time,
        "interval_days": str(account.interval_days) if account.interval_days is not None else None,
        "time_range": account.time_range,
        "watch_history": watch_history,
    }


def _replace_accounts(raw: Dict[str, Any], accounts: List[SubsonicAccount]) -> Dict[str, Any]:
    merged = dict(raw)
    section = dict(merged.get("subsonic") or {})
    section["account"] = [account.model_dump(exclude_none=True) for account in accounts]
    if "concurrency" not in section:
        section["concurrency"] = 1
    merged["subsonic"] = section
    return merged


def _generate_account_id(existing_ids: Set[str]) -> str:
    while True:
        account_id = uuid4().hex[:12]
        if account_id not in existing_ids:
            return account_id


def _account_key(account: SubsonicAccount) -> str:
    return str(account.id or "")


def _account_signature(account: SubsonicAccount) -> str:
    return f"{account.username}@{account.url}"


def _ensure_subsonic_account_ids(model: Config, raw: Dict[str, Any], accounts: List[SubsonicAccount]) -> Tuple[Config, Dict[str, Any], List[SubsonicAccount]]:
    existing_ids = {_account_key(account) for account in accounts if _account_key(account)}
    normalized: List[SubsonicAccount] = []
    changed = False

    for account in accounts:
        if _account_key(account):
            normalized.append(account)
            continue

        account_id = _generate_account_id(existing_ids)
        existing_ids.add(account_id)
        normalized.append(account.model_copy(update={"id": account_id}))
        changed = True

    if not changed:
        return model, raw, accounts

    merged = _replace_accounts(raw, normalized)
    validated = Config(**merged)
    serialized = validated.model_dump(mode='json', exclude_none=True, exclude_unset=True)
    _write_config_dict(serialized)
    persisted_accounts = list(validated.subsonic.account if validated.subsonic and validated.subsonic.account else [])
    return validated, serialized, persisted_accounts


def _load_subsonic_accounts() -> Tuple[Config, Dict[str, Any], List[SubsonicAccount]]:
    raw = _read_config_dict()
    model = Config(**raw)
    accounts = list(model.subsonic.account if model.subsonic and model.subsonic.account else [])
    return _ensure_subsonic_account_ids(model, raw, accounts)


@router.get("/subsonic/accounts")
async def list_subsonic_accounts(_: bool = Depends(require_auth)):
    try:
        cfg, _, accounts = _load_subsonic_accounts()
        items: List[Dict[str, Any]] = []
        summary = {
            "total": len(accounts),
            "enabled": 0,
            "use_proxy": 0,
            "module_enabled": bool(cfg.subsonic.enabled) if cfg.subsonic and cfg.subsonic.enabled is not None else True,
            "concurrency": cfg.subsonic.concurrency if cfg.subsonic and cfg.subsonic.concurrency is not None else 1,
            "time_range": str(cfg.subsonic.time_range) if cfg.subsonic and cfg.subsonic.time_range is not None else None,
            "interval_days": str(cfg.subsonic.interval_days) if cfg.subsonic and cfg.subsonic.interval_days is not None else None,
        }
        for account in accounts:
            item = _serialize_account(account)
            items.append(item)
            if item["enabled"]:
                summary["enabled"] += 1
            if item["use_proxy"]:
                summary["use_proxy"] += 1
        return {"accounts": items, "summary": summary}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list subsonic accounts: {exc}")


@router.post("/subsonic/settings")
async def save_subsonic_settings(payload: SubsonicSettingsPayload, _: bool = Depends(require_auth)):
    try:
        raw = _read_config_dict()
        merged = dict(raw)
        section = dict(merged.get("subsonic") or {})
        section["enabled"] = payload.enabled
        merged["subsonic"] = section

        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode='json', exclude_none=True, exclude_unset=True))
        return {"success": True}
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=format_errors(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save subsonic settings: {exc}")


@router.get("/subsonic/accounts/detail")
async def get_subsonic_account(key: str = Query(...), _: bool = Depends(require_auth)):
    try:
        _, _, accounts = _load_subsonic_accounts()
        for account in accounts:
            if _account_key(account) == key:
                return {"account": _serialize_account(account)}
        raise HTTPException(status_code=404, detail="Subsonic account not found")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load subsonic account: {exc}")


@router.post("/subsonic/accounts")
async def create_subsonic_account(payload: SubsonicAccountPayload, _: bool = Depends(require_auth)):
    try:
        _, raw, accounts = _load_subsonic_accounts()
        if any(_account_signature(existing) == f"{payload.username}@{payload.url}" for existing in accounts):
            raise HTTPException(status_code=409, detail="Subsonic account already exists")
        existing_ids = {_account_key(existing) for existing in accounts if _account_key(existing)}
        account = SubsonicAccount(id=_generate_account_id(existing_ids), **payload.model_dump(exclude_none=True))
        accounts.append(account)
        merged = _replace_accounts(raw, accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode='json', exclude_none=True, exclude_unset=True))
        return {"success": True, "account": _serialize_account(account)}
    except HTTPException:
        raise
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=format_errors(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create subsonic account: {exc}")


@router.put("/subsonic/accounts")
async def update_subsonic_account(key: str = Query(...), payload: SubsonicAccountPayload = None, _: bool = Depends(require_auth)):
    try:
        _, raw, accounts = _load_subsonic_accounts()
        updated = False
        next_accounts: List[SubsonicAccount] = []
        next_account: Optional[SubsonicAccount] = None
        for account in accounts:
            if _account_key(account) == key:
                payload_data = payload.model_dump(exclude_none=True)
                if not payload_data.get('password'):
                    payload_data['password'] = account.password
                next_account = SubsonicAccount(id=_account_key(account), **payload_data)
                next_accounts.append(next_account)
                updated = True
            else:
                next_accounts.append(account)
        if not updated:
            raise HTTPException(status_code=404, detail="Subsonic account not found")
        if sum(1 for account in next_accounts if _account_signature(account) == _account_signature(next_account)) > 1:
            raise HTTPException(status_code=409, detail="Subsonic account already exists")
        merged = _replace_accounts(raw, next_accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode='json', exclude_none=True, exclude_unset=True))
        return {"success": True, "account": _serialize_account(next_account)}
    except HTTPException:
        raise
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=format_errors(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update subsonic account: {exc}")


@router.delete("/subsonic/accounts")
async def delete_subsonic_account(key: str = Query(...), _: bool = Depends(require_auth)):
    try:
        _, raw, accounts = _load_subsonic_accounts()
        next_accounts = [account for account in accounts if _account_key(account) != key]
        if len(next_accounts) == len(accounts):
            raise HTTPException(status_code=404, detail="Subsonic account not found")
        merged = _replace_accounts(raw, next_accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode='json', exclude_none=True, exclude_unset=True))
        return {"success": True}
    except HTTPException:
        raise
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=format_errors(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete subsonic account: {exc}")
