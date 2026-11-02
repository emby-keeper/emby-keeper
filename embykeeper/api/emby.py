import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field, ValidationError

from .auth import require_auth
from .config import _read_config_dict, _write_config_dict
from .runinfo import _sort_datetime
from ..cache import cache
from ..schema import Config, EmbyAccount, format_errors
from ..config import config as config_manager
from ..runinfo import RunContext, RunStatus
from ..emby.api import Emby, EmbyError
from ..emby.main import EmbyManager

router = APIRouter()

EMBY_ACCOUNT_HISTORY_LIMIT = 30
EMBY_ACCOUNT_RUN_HISTORY_LIMIT = 20


class EmbyAccountPayload(BaseModel):
    url: str
    username: str
    password: str = ""
    name: Optional[str] = None
    enabled: bool = True
    use_proxy: bool = True
    allow_stream: bool = False
    cf_challenge: bool = True
    allow_multiple: bool = True
    play_id: Optional[str] = None
    time: List[int] = Field(default_factory=lambda: [300, 600])
    interval_days: Optional[str] = None
    time_range: Optional[str] = None


class EmbySettingsPayload(BaseModel):
    enabled: bool = True


class EmbyPlayIdProbePayload(BaseModel):
    url: str
    username: str
    password: str = ""
    name: Optional[str] = None
    use_proxy: bool = True
    cf_challenge: bool = True
    play_id: str


def _load_config() -> Config:
    return Config(**_read_config_dict())


def _generate_account_id(existing_ids: Set[str]) -> str:
    while True:
        account_id = uuid4().hex[:12]
        if account_id not in existing_ids:
            return account_id


def _account_key(account: EmbyAccount) -> str:
    return str(account.id or "")


def _account_signature(account: EmbyAccount) -> str:
    return f"{account.username}@{account.url}"


def _account_history_cache_key(account: EmbyAccount) -> str:
    return f"emby.account_history.{account.url.host}.{account.username}"


def _site_title_cache_key(account: EmbyAccount) -> str:
    return f"emby.site_title.{account.url.host}"


def _device_cache_key(account: EmbyAccount) -> str:
    return f"emby.env.{account.url.host}.{account.username}"


def _normalize_history_records(records: Any) -> List[Dict[str, str]]:
    normalized: List[Dict[str, str]] = []
    if not isinstance(records, list):
        return normalized

    for record in records:
        if not isinstance(record, dict):
            continue

        status = record.get("status")
        time_value = record.get("time")
        if status not in {"success", "failed"} or not isinstance(time_value, str):
            continue

        normalized.append({"status": status, "time": time_value})

    normalized.sort(key=lambda item: item["time"], reverse=True)
    return normalized[:EMBY_ACCOUNT_HISTORY_LIMIT]


def _hostname_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname:
        return parsed.hostname
    return url.split("://", 1)[-1].split("/", 1)[0]


def _get_cached_site_title(account: EmbyAccount) -> Optional[str]:
    cached_title = cache.get(_site_title_cache_key(account))
    return cached_title if isinstance(cached_title, str) and cached_title.strip() else None


def _card_title(account: EmbyAccount) -> str:
    return _get_cached_site_title(account) or account.url.host


def _card_subtitle(account: EmbyAccount) -> str:
    return account.name or account.username


def _read_account_history(account: EmbyAccount) -> List[Dict[str, str]]:
    return _normalize_history_records(cache.get(_account_history_cache_key(account), []))


def _account_spec(account: EmbyAccount) -> str:
    return f"{account.username}@{account.name or account.url.host}"


def _account_run_descriptions(account: EmbyAccount) -> Set[str]:
    spec = _account_spec(account)
    return {
        f"Emby 保活任务 - {spec}",
        f"Emby 测试运行 - {spec}",
        "使用全局设置的 Emby 统一保活",
    }


def _account_log_target(account: EmbyAccount) -> str:
    return _account_spec(account)


def _match_account_run(ctx: RunContext, account: EmbyAccount) -> bool:
    if ctx.description not in _account_run_descriptions(account):
        return False

    if ctx.description != "使用全局设置的 Emby 统一保活":
        return True

    target = _account_log_target(account)
    for log in ctx.yield_logs(reverse=True):
        message = str(log.message or "")
        if target in message and (
            "保活成功" in message or "保活失败" in message or "正在登陆" in message or "成功登陆" in message
        ):
            return True
    return False


def _serialize_run_summary(ctx: RunContext) -> Dict[str, Any]:
    return {
        "id": ctx.id,
        "description": ctx.description,
        "status": ctx.status.name if ctx.status is not None else None,
        "status_code": int(ctx.status) if ctx.status is not None else None,
        "status_info": ctx.status_info,
        "duration": ctx.duration,
        "start_time": ctx.start_time.isoformat() if ctx.start_time else None,
        "end_time": ctx.end_time.isoformat() if ctx.end_time else None,
        "parent_ids": ctx.parent_ids or [],
        "child_count": len(cache.get(f"runinfo.children.{ctx.id}", []) or []),
    }


def _account_run_history(
    account: EmbyAccount, limit: int = EMBY_ACCOUNT_RUN_HISTORY_LIMIT
) -> List[Dict[str, Any]]:
    contexts = [ctx for ctx in RunContext.list_all() if _match_account_run(ctx, account)]
    contexts.sort(key=lambda ctx: _sort_datetime(ctx.end_time or ctx.start_time), reverse=True)
    return [_serialize_run_summary(ctx) for ctx in contexts[:limit]]


def _read_cached_device(account: EmbyAccount) -> Optional[Dict[str, Any]]:
    cached = cache.get(_device_cache_key(account), {})
    if not isinstance(cached, dict):
        return None

    cleaned = {
        "client": cached.get("client"),
        "device": cached.get("device"),
        "device_id": cached.get("device_id"),
        "client_version": cached.get("client_version"),
        "useragent": cached.get("useragent") or cached.get("ua"),
    }
    if not any(cleaned.values()):
        return None
    return cleaned


def _find_account_by_key(account_key: str) -> EmbyAccount:
    _, _, accounts = _load_emby_accounts()
    for account in accounts:
        if _account_key(account) == account_key:
            return account
    raise HTTPException(status_code=404, detail="Emby account not found")


async def _run_single_account(account: EmbyAccount, description: Optional[str] = None):
    manager = EmbyManager()
    test_account = account.model_copy(update={"enabled": True})
    result = await manager._watch_main(
        [test_account], instant=True, description=description, connect_only=True
    )
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to start Emby test run")
    return result


def _record_account_watch_result(account: EmbyAccount, success: bool, run_time: Optional[datetime] = None):
    timestamp = (run_time or datetime.now()).isoformat()
    history = _read_account_history(account)
    history.insert(0, {"status": "success" if success else "failed", "time": timestamp})
    cache.set(_account_history_cache_key(account), history[:EMBY_ACCOUNT_HISTORY_LIMIT])


def _hydrate_account_history_from_runinfo(account: EmbyAccount) -> List[Dict[str, str]]:
    history = _read_account_history(account)
    if len(history) >= EMBY_ACCOUNT_HISTORY_LIMIT:
        return history

    target_spec = f"{account.username}@{account.name or account.url.host}"
    collected = list(history)
    seen_times = {record["time"] for record in collected}

    contexts = sorted(
        RunContext.list_all(),
        key=lambda ctx: _sort_datetime(ctx.end_time or ctx.start_time),
        reverse=True,
    )

    for ctx in contexts:
        if len(collected) >= EMBY_ACCOUNT_HISTORY_LIMIT:
            break
        if ctx.description not in {"使用全局设置的 Emby 统一保活", f"Emby 保活任务 - {target_spec}"}:
            continue
        if ctx.status in {RunStatus.PENDING, RunStatus.INITIALIZING, RunStatus.RUNNING, RunStatus.CATAGORY}:
            continue

        logs = [log.message for log in ctx.yield_logs(reverse=True)]
        matched = False
        status = None
        for message in logs:
            if target_spec not in message:
                continue
            if "保活成功" in message:
                status = "success"
                matched = True
                break
            if "保活失败" in message:
                status = "failed"
                matched = True
                break

        if not matched:
            continue

        run_time = ctx.end_time or ctx.start_time
        if not run_time:
            continue

        time_value = run_time.isoformat()
        if time_value in seen_times:
            continue

        collected.append({"status": status, "time": time_value})
        seen_times.add(time_value)

    collected.sort(key=lambda item: item["time"], reverse=True)
    trimmed = collected[:EMBY_ACCOUNT_HISTORY_LIMIT]
    if trimmed:
        cache.set(_account_history_cache_key(account), trimmed)
    return trimmed


def _serialize_account(account: EmbyAccount) -> Dict[str, Any]:
    watch_history = _hydrate_account_history_from_runinfo(account)
    return {
        "id": _account_key(account),
        "url": str(account.url),
        "username": account.username,
        "name": account.name,
        "site_title": _get_cached_site_title(account),
        "card_title": _card_title(account),
        "card_subtitle": _card_subtitle(account),
        "enabled": bool(account.enabled),
        "allow_stream": bool(account.allow_stream),
        "use_proxy": bool(account.use_proxy),
        "cf_challenge": bool(account.cf_challenge),
        "allow_multiple": bool(account.allow_multiple),
        "play_id": account.play_id,
        "time": account.time,
        "interval_days": str(account.interval_days) if account.interval_days is not None else None,
        "time_range": account.time_range,
        "watch_history": watch_history,
        "hostname": _hostname_from_url(str(account.url)),
        "device_cache": _read_cached_device(account),
        "run_history": _account_run_history(account),
    }


def _replace_accounts(raw: Dict[str, Any], accounts: List[EmbyAccount]) -> Dict[str, Any]:
    merged = dict(raw)
    emby_section = dict(merged.get("emby") or {})
    emby_section["account"] = [account.model_dump(exclude_none=True) for account in accounts]
    if "concurrency" not in emby_section:
        emby_section["concurrency"] = 1
    merged["emby"] = emby_section
    return merged


def _ensure_emby_account_ids(
    model: Config, raw: Dict[str, Any], accounts: List[EmbyAccount]
) -> Tuple[Config, Dict[str, Any], List[EmbyAccount]]:
    existing_ids = {_account_key(account) for account in accounts if _account_key(account)}
    normalized: List[EmbyAccount] = []
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
    serialized = validated.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    _write_config_dict(serialized)
    persisted_accounts = list(validated.emby.account if validated.emby and validated.emby.account else [])
    return validated, serialized, persisted_accounts


def _load_emby_accounts() -> Tuple[Config, Dict[str, Any], List[EmbyAccount]]:
    raw = _read_config_dict()
    model = Config(**raw)
    accounts = list(model.emby.account if model.emby and model.emby.account else [])
    return _ensure_emby_account_ids(model, raw, accounts)


@router.get("/emby/accounts")
async def list_emby_accounts(_: bool = Depends(require_auth)):
    try:
        cfg, _, accounts = _load_emby_accounts()
        items: List[Dict] = []
        summary = {
            "total": len(accounts),
            "enabled": 0,
            "use_proxy": 0,
            "allow_stream": 0,
            "cf_challenge": 0,
            "module_enabled": bool(cfg.emby.enabled) if cfg.emby and cfg.emby.enabled is not None else True,
            "concurrency": cfg.emby.concurrency if cfg.emby and cfg.emby.concurrency is not None else 1,
            "time_range": str(cfg.emby.time_range) if cfg.emby and cfg.emby.time_range is not None else None,
            "interval_days": (
                str(cfg.emby.interval_days) if cfg.emby and cfg.emby.interval_days is not None else None
            ),
        }
        for a in accounts:
            status = _serialize_account(a)
            items.append(status)
            if status["enabled"]:
                summary["enabled"] += 1
            if status["use_proxy"]:
                summary["use_proxy"] += 1
            if status["allow_stream"]:
                summary["allow_stream"] += 1
            if status["cf_challenge"]:
                summary["cf_challenge"] += 1
        return {"accounts": items, "summary": summary}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list emby accounts: {e}")


@router.post("/emby/settings")
async def save_emby_settings(payload: EmbySettingsPayload, _: bool = Depends(require_auth)):
    try:
        raw = _read_config_dict()
        merged = dict(raw)
        emby_section = dict(merged.get("emby") or {})
        emby_section["enabled"] = payload.enabled
        merged["emby"] = emby_section

        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
        return {"success": True}
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save emby settings: {e}")


@router.get("/emby/accounts/detail")
async def get_emby_account(key: str = Query(...), _: bool = Depends(require_auth)):
    try:
        account = _find_account_by_key(key)
        return {"account": _serialize_account(account)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load emby account: {e}")


@router.get("/emby/accounts/runs")
async def get_emby_account_runs(key: str = Query(...), limit: int = 20, _: bool = Depends(require_auth)):
    try:
        account = _find_account_by_key(key)
        safe_limit = max(1, min(limit, 100))
        return {"runs": _account_run_history(account, limit=safe_limit)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load emby account runs: {e}")


@router.get("/emby/accounts/device")
async def get_emby_account_device(key: str = Query(...), _: bool = Depends(require_auth)):
    try:
        account = _find_account_by_key(key)
        return {"device": _read_cached_device(account)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load emby account device cache: {e}")


@router.post("/emby/accounts/test-run")
async def start_emby_account_test_run(
    key: Optional[str] = Query(None),
    payload: Optional[EmbyAccountPayload] = None,
    _: bool = Depends(require_auth),
):
    try:
        if key:
            account = _find_account_by_key(key)
            if payload is not None:
                payload_data = payload.model_dump(exclude_none=True)
                if not payload_data.get("password"):
                    payload_data["password"] = account.password
                account = EmbyAccount(id=_account_key(account), **payload_data)
        elif payload is not None:
            account = EmbyAccount(id=_generate_account_id(set()), **payload.model_dump(exclude_none=True))
        else:
            raise HTTPException(status_code=400, detail="key or account payload required")

        description = f"Emby 测试运行 - {_account_spec(account)}"
        existing_ids = {ctx.id for ctx in RunContext.list_all()}
        task = asyncio.create_task(_run_single_account(account, description=description))

        run_id = None
        for _ in range(30):
            for ctx in RunContext.list_all():
                if ctx.id not in existing_ids and ctx.description == description:
                    run_id = ctx.id
                    break

            if run_id:
                break

            if task.done():
                break

            await asyncio.sleep(0.1)

        if not run_id and task.done() and not task.cancelled():
            result = task.result()
            run_id = result.id if result else None

        return {"success": True, "run_id": run_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start emby account test run: {e}")


@router.post("/emby/accounts/probe-item")
async def probe_emby_play_item(
    payload: EmbyPlayIdProbePayload,
    key: Optional[str] = Query(None),
    _: bool = Depends(require_auth),
):
    """Log in with the supplied credentials and resolve the given play ID to an item.

    This is the lightweight counterpart of the test-run endpoint: it only verifies
    that the account can log in and that the configured video ID exists, without
    actually starting a playback task.
    """
    play_id = (payload.play_id or "").strip()
    if not play_id:
        raise HTTPException(status_code=400, detail="请先填写播放 ID")

    try:
        password = payload.password
        account_id: Optional[str] = None

        if key:
            existing = _find_account_by_key(key)
            account_id = _account_key(existing)
            if not password:
                password = existing.password

        if not account_id:
            account_id = _generate_account_id(set())

        account_data: Dict[str, Any] = {
            "id": account_id,
            "url": payload.url,
            "username": payload.username,
            "password": password,
            "use_proxy": payload.use_proxy,
            "cf_challenge": payload.cf_challenge,
            "play_id": play_id,
        }
        if payload.name:
            account_data["name"] = payload.name

        account = EmbyAccount(**account_data)

        emby = Emby(account)
        emby.log = logger.bind(server=account.name or emby.hostname, username=account.username)

        if not emby.user_id and not await emby.login():
            raise HTTPException(status_code=400, detail="登录失败, 无法访问该站点")

        item = await emby.get_item(play_id)
        if not item or not item.get("Id"):
            raise HTTPException(status_code=404, detail="未找到该视频项目, 请确认播放 ID 是否正确")

        try:
            duration_seconds = round(int(item.get("RunTimeTicks") or 0) / 10_000_000)
        except (TypeError, ValueError):
            duration_seconds = 0

        return {
            "success": True,
            "item": {
                "id": item.get("Id"),
                "name": item.get("Name"),
                "type": item.get("Type"),
                "series": item.get("SeriesName"),
                "year": item.get("ProductionYear"),
                "duration_seconds": duration_seconds,
            },
        }
    except HTTPException:
        raise
    except EmbyError as e:
        raise HTTPException(status_code=400, detail=f"测试播放 ID 失败: {e}")
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"测试播放 ID 失败: {e}")


@router.post("/emby/accounts")
async def create_emby_account(payload: EmbyAccountPayload, _: bool = Depends(require_auth)):
    try:
        _, raw, accounts = _load_emby_accounts()

        if any(_account_signature(existing) == f"{payload.username}@{payload.url}" for existing in accounts):
            raise HTTPException(status_code=409, detail="Emby account already exists")

        existing_ids = {_account_key(existing) for existing in accounts if _account_key(existing)}
        account = EmbyAccount(id=_generate_account_id(existing_ids), **payload.model_dump(exclude_none=True))

        accounts.append(account)
        merged = _replace_accounts(raw, accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
        return {"success": True, "account": _serialize_account(account)}
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create emby account: {e}")


@router.put("/emby/accounts")
async def update_emby_account(
    key: str = Query(...), payload: EmbyAccountPayload = None, _: bool = Depends(require_auth)
):
    try:
        _, raw, accounts = _load_emby_accounts()
        updated = False
        next_accounts: List[EmbyAccount] = []
        next_account: Optional[EmbyAccount] = None

        for account in accounts:
            if _account_key(account) == key:
                payload_data = payload.model_dump(exclude_unset=True)
                if not payload_data.get("password"):
                    payload_data["password"] = account.password
                account_data = account.model_dump(exclude_none=False)
                account_data.update(payload_data)
                account_data["id"] = _account_key(account)
                next_account = EmbyAccount(**account_data)
                next_accounts.append(next_account)
                updated = True
            else:
                next_accounts.append(account)

        if not updated:
            raise HTTPException(status_code=404, detail="Emby account not found")

        if (
            sum(
                1
                for account in next_accounts
                if _account_signature(account) == _account_signature(next_account)
            )
            > 1
        ):
            raise HTTPException(status_code=409, detail="Emby account already exists")

        merged = _replace_accounts(raw, next_accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
        return {"success": True, "account": _serialize_account(next_account)}
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update emby account: {e}")


@router.delete("/emby/accounts")
async def delete_emby_account(key: str = Query(...), _: bool = Depends(require_auth)):
    try:
        _, raw, accounts = _load_emby_accounts()
        next_accounts = [account for account in accounts if _account_key(account) != key]

        if len(next_accounts) == len(accounts):
            raise HTTPException(status_code=404, detail="Emby account not found")

        merged = _replace_accounts(raw, next_accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
        return {"success": True}
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete emby account: {e}")
