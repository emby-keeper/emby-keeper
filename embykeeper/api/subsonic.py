import asyncio
from typing import Any, Dict, List, Optional, Set, Tuple
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ValidationError

from .auth import require_auth
from .config import _read_config_dict, _write_config_dict
from .runinfo import _sort_datetime
from ..cache import cache
from ..config import config as config_manager
from ..schema import Config, SubsonicAccount, format_errors
from ..runinfo import RunContext, RunStatus
from ..subsonic.main import SubsonicManager

router = APIRouter()

SUBSONIC_ACCOUNT_HISTORY_LIMIT = 30
SUBSONIC_ACCOUNT_RUN_HISTORY_LIMIT = 20


class SubsonicAccountPayload(BaseModel):
    url: str
    username: str
    password: str = ""
    name: Optional[str] = None
    enabled: bool = True
    use_proxy: bool = True
    time: List[int] = Field(default_factory=lambda: [300, 600])
    interval_days: Optional[str] = None
    time_range: Optional[str] = None


class SubsonicSettingsPayload(BaseModel):
    enabled: bool = True


def _load_config() -> Config:
    return Config(**_read_config_dict())


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
        "run_history": _account_run_history(account),
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


def _account_spec(account: SubsonicAccount) -> str:
    return f"{account.username}@{account.name or account.url.host}"


def _account_run_descriptions(account: SubsonicAccount) -> Set[str]:
    spec = _account_spec(account)
    return {
        f"Subsonic 保活任务 - {spec}",
        f"Subsonic 测试运行 - {spec}",
        "使用全局设置的 Subsonic 统一保活",
        "Subsonic 保活任务",
    }


def _match_account_run(ctx: RunContext, account: SubsonicAccount) -> bool:
    if ctx.description not in _account_run_descriptions(account):
        return False

    if ctx.description not in {"使用全局设置的 Subsonic 统一保活", "Subsonic 保活任务"}:
        return True

    target = _account_spec(account)
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
    account: SubsonicAccount, limit: int = SUBSONIC_ACCOUNT_RUN_HISTORY_LIMIT
) -> List[Dict[str, Any]]:
    contexts = [ctx for ctx in RunContext.list_all() if _match_account_run(ctx, account)]
    contexts.sort(key=lambda ctx: _sort_datetime(ctx.end_time or ctx.start_time), reverse=True)
    return [_serialize_run_summary(ctx) for ctx in contexts[:limit]]


def _find_account_by_key(account_key: str) -> SubsonicAccount:
    _, _, accounts = _load_subsonic_accounts()
    for account in accounts:
        if _account_key(account) == account_key:
            return account
    raise HTTPException(status_code=404, detail="Subsonic account not found")


async def _run_single_account(account: SubsonicAccount, description: Optional[str] = None):
    manager = SubsonicManager()
    test_account = account.model_copy(update={"enabled": True})
    result = await manager._listen_main(
        [test_account], instant=True, description=description, connect_only=True
    )
    if result is None:
        raise HTTPException(status_code=500, detail="Failed to start Subsonic test run")
    return result


@router.post("/subsonic/accounts/test-run")
async def start_subsonic_account_test_run(
    key: Optional[str] = Query(None),
    payload: Optional[SubsonicAccountPayload] = None,
    _: bool = Depends(require_auth),
):
    try:
        if key:
            _, _, accounts = _load_subsonic_accounts()
            account = next((item for item in accounts if _account_key(item) == key), None)
            if account is None:
                raise HTTPException(status_code=404, detail="Subsonic account not found")
            if payload is not None:
                payload_data = payload.model_dump(exclude_none=True)
                if not payload_data.get("password"):
                    payload_data["password"] = account.password
                account = SubsonicAccount(id=_account_key(account), **payload_data)
        elif payload is not None:
            account = SubsonicAccount(id=_generate_account_id(set()), **payload.model_dump(exclude_none=True))
        else:
            raise HTTPException(status_code=400, detail="key or account payload required")

        description = f"Subsonic 测试运行 - {_account_spec(account)}"
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
        raise HTTPException(status_code=500, detail=f"Failed to start subsonic account test run: {e}")


def _ensure_subsonic_account_ids(
    model: Config, raw: Dict[str, Any], accounts: List[SubsonicAccount]
) -> Tuple[Config, Dict[str, Any], List[SubsonicAccount]]:
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
    serialized = validated.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    _write_config_dict(serialized)
    persisted_accounts = list(
        validated.subsonic.account if validated.subsonic and validated.subsonic.account else []
    )
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
            "module_enabled": (
                bool(cfg.subsonic.enabled) if cfg.subsonic and cfg.subsonic.enabled is not None else True
            ),
            "concurrency": (
                cfg.subsonic.concurrency if cfg.subsonic and cfg.subsonic.concurrency is not None else 1
            ),
            "time_range": (
                str(cfg.subsonic.time_range) if cfg.subsonic and cfg.subsonic.time_range is not None else None
            ),
            "interval_days": (
                str(cfg.subsonic.interval_days)
                if cfg.subsonic and cfg.subsonic.interval_days is not None
                else None
            ),
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
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
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


@router.get("/subsonic/accounts/runs")
async def get_subsonic_account_runs(key: str = Query(...), limit: int = 20, _: bool = Depends(require_auth)):
    try:
        account = _find_account_by_key(key)
        safe_limit = max(1, min(limit, 100))
        return {"runs": _account_run_history(account, limit=safe_limit)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to load subsonic account runs: {exc}")


@router.post("/subsonic/accounts")
async def create_subsonic_account(payload: SubsonicAccountPayload, _: bool = Depends(require_auth)):
    try:
        _, raw, accounts = _load_subsonic_accounts()
        if any(_account_signature(existing) == f"{payload.username}@{payload.url}" for existing in accounts):
            raise HTTPException(status_code=409, detail="Subsonic account already exists")
        existing_ids = {_account_key(existing) for existing in accounts if _account_key(existing)}
        account = SubsonicAccount(
            id=_generate_account_id(existing_ids), **payload.model_dump(exclude_none=True)
        )
        accounts.append(account)
        merged = _replace_accounts(raw, accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
        return {"success": True, "account": _serialize_account(account)}
    except HTTPException:
        raise
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=format_errors(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create subsonic account: {exc}")


@router.put("/subsonic/accounts")
async def update_subsonic_account(
    key: str = Query(...), payload: SubsonicAccountPayload = None, _: bool = Depends(require_auth)
):
    try:
        _, raw, accounts = _load_subsonic_accounts()
        updated = False
        next_accounts: List[SubsonicAccount] = []
        next_account: Optional[SubsonicAccount] = None
        for account in accounts:
            if _account_key(account) == key:
                payload_data = payload.model_dump(exclude_unset=True)
                if not payload_data.get("password"):
                    payload_data["password"] = account.password
                account_data = account.model_dump(exclude_none=False)
                account_data.update(payload_data)
                account_data["id"] = _account_key(account)
                next_account = SubsonicAccount(**account_data)
                next_accounts.append(next_account)
                updated = True
            else:
                next_accounts.append(account)
        if not updated:
            raise HTTPException(status_code=404, detail="Subsonic account not found")
        if (
            sum(
                1
                for account in next_accounts
                if _account_signature(account) == _account_signature(next_account)
            )
            > 1
        ):
            raise HTTPException(status_code=409, detail="Subsonic account already exists")
        merged = _replace_accounts(raw, next_accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
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
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
        return {"success": True}
    except HTTPException:
        raise
    except ValidationError as exc:
        raise HTTPException(status_code=400, detail=format_errors(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete subsonic account: {exc}")
