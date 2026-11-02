import asyncio
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError

from .auth import require_auth
from .config import _read_config_dict, _write_config_dict
from .runinfo import _sort_datetime
from ..schema import Config, TelegramAccount, TelegramConfig, format_errors
from ..config import config as config_manager
from ..runinfo import RunContext, RunStatus
from ..cache import cache
from ..telegram.session import (
    API_HASH,
    API_ID,
    ClientsSession,
    build_pyrogram_client_params,
    convert_telethon_session_string,
    get_telethon_proxy,
    is_valid_pyrogram_session_string,
)
from ..telegram.pyrogram import Client
from ..telegram.dynamic import get_display_names, get_names
from .sites import SITE_TYPES, _custom_sites, _read_config_dict as _read_sites_config

router = APIRouter()


class TelegramSitePayload(BaseModel):
    checkiner: Optional[List[str]] = None
    monitor: Optional[List[str]] = None
    messager: Optional[List[str]] = None
    registrar: Optional[List[str]] = None


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
    site: Optional[TelegramSitePayload] = None


class TelegramSettingsPayload(BaseModel):
    checkiner_enabled: bool = True
    monitor_enabled: bool = True
    messager_enabled: bool = True
    registrar_enabled: bool = True


def _load_config() -> Config:
    return Config(**_read_config_dict())


def _account_from_payload(
    payload: TelegramAccountPayload,
    existing: Optional[TelegramAccount] = None,
) -> TelegramAccount:
    """Build an account from a payload, normalizing the per-account site override.

    An empty site override (no module configured) is stored as ``None`` so that
    the account keeps inheriting the global ``site`` configuration.
    """
    data = existing.model_dump(exclude_none=False) if existing else {}
    payload_data = payload.model_dump(exclude_unset=existing is not None, exclude_none=existing is None)
    data.update(payload_data)

    if "site" in payload_data:
        site = data.get("site")
        if isinstance(site, dict):
            site = {key: value for key, value in site.items() if value is not None}
        data["site"] = site or None

    return TelegramAccount(**data)


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
        "site": account.site.model_dump(exclude_none=True) if account.site else None,
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

    return latest_status, (
        latest_time.isoformat() if latest_time and latest_time != _sort_datetime(None) else None
    )


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
            "checkiner_enabled": (
                bool(cfg.checkiner.enabled) if cfg.checkiner and cfg.checkiner.enabled is not None else True
            ),
            "monitor_enabled": (
                bool(cfg.monitor.enabled) if cfg.monitor and cfg.monitor.enabled is not None else True
            ),
            "messager_enabled": (
                bool(cfg.messager.enabled) if cfg.messager and cfg.messager.enabled is not None else True
            ),
            "registrar_enabled": (
                bool(cfg.registrar.enabled) if cfg.registrar and cfg.registrar.enabled is not None else True
            ),
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
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
        return {"success": True}
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save telegram settings: {e}")


@router.get("/telegram/sites")
async def get_telegram_sites(_: bool = Depends(require_auth)):
    """List the preset site names for each telegram module.

    ``sites`` mirrors the "默认启用站点" preset, ``all_sites`` the
    "全部可用站点" preset (``allow_ignore=True``): sites flagged as ignored are
    still usable when named explicitly, and for some modules (messager /
    registrar) they are the only option.

    ``custom`` lists the template sites configured in the config file, so that
    the site scope selector can always offer them even when they are not
    currently part of the site list.
    """
    try:
        raw = _read_sites_config()
        custom: Dict[str, List[str]] = {}
        custom_names: Dict[str, Dict[str, str]] = {}
        for site_type in SITE_TYPES:
            items = [item for item in _custom_sites(raw, site_type) if not item.get("builtin")]
            custom[site_type] = [item["name"] for item in items]
            custom_names[site_type] = {
                item["name"]: str(item.get("display_name") or item["name"]) for item in items
            }

        return {
            "sites": {site_type: get_names(site_type) for site_type in SITE_TYPES},
            "all_sites": {site_type: get_names(site_type, allow_ignore=True) for site_type in SITE_TYPES},
            "custom": custom,
            "display_names": {
                site_type: {**get_display_names(site_type), **custom_names.get(site_type, {})}
                for site_type in SITE_TYPES
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load telegram sites: {e}")


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
        account = _account_from_payload(payload)

        if any(existing.phone == account.phone for existing in accounts):
            raise HTTPException(status_code=409, detail="Telegram account already exists")

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
        raise HTTPException(status_code=500, detail=f"Failed to create telegram account: {e}")


@router.put("/telegram/accounts/{phone}")
async def update_telegram_account(
    phone: str, payload: TelegramAccountPayload, _: bool = Depends(require_auth)
):
    try:
        _, raw, accounts = _load_telegram_accounts()
        next_account = _account_from_payload(payload)
        updated = False
        next_accounts: List[TelegramAccount] = []

        for account in accounts:
            if account.phone == phone:
                next_account = _account_from_payload(payload, account)
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
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
        return {"success": True, "account": _serialize_account(next_account)}
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update telegram account: {e}")


_pending_logins: Dict[str, Dict[str, Any]] = {}


async def _run_telegram_login(account: TelegramAccount, login_id: str):
    from telethon import TelegramClient, errors
    from telethon.sessions import StringSession
    from .. import __version__ as app_version, var

    entry = _pending_logins.get(login_id)
    if entry is None:
        return

    queue: asyncio.Queue = entry["queue"]
    use_proxy = bool(config_manager.telegram and config_manager.telegram.use_proxy)
    proxy = get_telethon_proxy(config_manager.proxy if use_proxy else None)

    client = None
    try:
        with tempfile.NamedTemporaryFile() as tmp_file:
            client = TelegramClient(
                tmp_file.name,
                api_id=account.api_id or API_ID,
                api_hash=account.api_hash or API_HASH,
                system_version="4.16.30-vxEmby",
                device_model="A320MH",
                app_version=app_version,
                proxy=proxy,
            )
            if var.telegram_test_server:
                from ..telegram.session import _test_dc_id, _test_dc_ip, _test_dc_port

                client.session.set_dc(_test_dc_id, _test_dc_ip, _test_dc_port)

            entry["state"] = "connecting"
            entry["message"] = "正在连接 Telegram 服务器…"

            async def _connect_and_request_code():
                await client.connect()
                await client.send_code_request(account.phone)

            connect_task = asyncio.create_task(_connect_and_request_code())
            done, _ = await asyncio.wait({connect_task}, timeout=30)
            if not done:
                connect_task.cancel()
                entry["state"] = "failed"
                entry["message"] = "连接 Telegram 服务器超时，请检查网络或代理配置后重试。"
                return
            connect_task.result()

            entry["state"] = "waiting_code"
            entry["message"] = "验证码已发送到手机上的 Telegram，请查收后输入。"

            while True:
                item = await asyncio.wait_for(queue.get(), timeout=180)

                async def _sign_in_and_fetch():
                    if item.get("kind") == "password":
                        return await client.sign_in(phone=account.phone, password=item.get("value"))
                    return await client.sign_in(account.phone, code=item.get("value"))

                sign_task = asyncio.create_task(_sign_in_and_fetch())
                done, _ = await asyncio.wait({sign_task}, timeout=30)
                if not done:
                    sign_task.cancel()
                    entry["state"] = "failed"
                    entry["message"] = "提交超时，请检查网络或代理配置后重试。"
                    return
                try:
                    sign_task.result()
                except errors.SessionPasswordNeededError:
                    entry["state"] = "need_password"
                    entry["message"] = "该账号启用了两步验证，请输入密码。"
                    continue
                except errors.PasswordHashInvalidError:
                    entry["state"] = "password_error"
                    entry["message"] = "两步验证密码错误，请重新输入。"
                    continue
                except (
                    errors.PhoneCodeInvalidError,
                    errors.PhoneCodeExpiredError,
                    errors.PhoneCodeEmptyError,
                    errors.PhoneCodeHashEmptyError,
                ):
                    entry["state"] = "code_error"
                    entry["message"] = "验证码错误或已过期，请重新输入。"
                    continue

                me_task = asyncio.create_task(client.get_me())
                done, _ = await asyncio.wait({me_task}, timeout=30)
                if not done:
                    me_task.cancel()
                    entry["state"] = "failed"
                    entry["message"] = "获取登录信息超时，请重新测试。"
                    return
                me = me_task.result()
                session_str = convert_telethon_session_string(
                    StringSession.save(client.session),
                    account.api_id or API_ID,
                    var.telegram_test_server,
                    me.id,
                    int(me.bot),
                )
                session_key = f"telegram.session_str.{account.get_config_key()}"
                cache.set(session_key, session_str)
                display_name = me.first_name or account.phone
                entry["state"] = "done"
                entry["success"] = True
                entry["session"] = session_str
                entry["message"] = f"登录成功，当前账号「{display_name}」。登录状态已保存。"
                return
    except asyncio.TimeoutError:
        entry["state"] = "failed"
        entry["message"] = "等待输入超时，登录已取消，请重新测试。"
    except errors.PhoneNumberInvalidError:
        entry["state"] = "failed"
        entry["message"] = "手机号格式错误或未注册，请检查后重试。"
    except errors.PhoneNumberBannedError:
        entry["state"] = "failed"
        entry["message"] = "该手机号已被 Telegram 封禁，无法登录。"
    except errors.ApiIdPublishedFloodError:
        entry["state"] = "failed"
        entry["message"] = "API 使用频率受限，请稍后重试或更换 API ID/Hash。"
    except errors.FloodWaitError as e:
        entry["state"] = "failed"
        entry["message"] = f"Telegram 限流中，请等待 {getattr(e, 'seconds', 60)} 秒后重试。"
    except Exception as e:
        entry["state"] = "failed"
        entry["message"] = f"登录失败：{e}"
    finally:
        if client is not None:
            try:
                await client.disconnect()
            except Exception:
                pass


async def _start_code_login(account: TelegramAccount) -> Dict[str, Any]:
    login_id = uuid.uuid4().hex[:12]
    _pending_logins[login_id] = {
        "queue": asyncio.Queue(),
        "state": "starting",
        "message": "正在连接 Telegram 服务器…",
        "success": False,
        "session": None,
    }
    asyncio.create_task(_run_telegram_login(account, login_id))
    return {"success": False, "needs_code": True, "login_id": login_id}


@router.post("/telegram/accounts/test")
async def test_telegram_account(payload: TelegramAccountPayload, _: bool = Depends(require_auth)):
    try:
        account = TelegramAccount(**payload.model_dump(exclude_none=True))

        session_str = account.session
        from_cache = False
        if not session_str:
            session_str = cache.get(f"telegram.session_str.{account.get_config_key()}")
            from_cache = True
        if not session_str:
            return await _start_code_login(account)
        if not is_valid_pyrogram_session_string(session_str):
            if from_cache:
                cache.delete(f"telegram.session_str.{account.get_config_key()}")
                return await _start_code_login(account)
            return {"success": False, "message": "填写的 Session 无效或已损坏，请清空后重新测试登录。"}

        use_proxy = bool(config_manager.telegram and config_manager.telegram.use_proxy)
        client_params = build_pyrogram_client_params(
            account.phone,
            session_str,
            account.api_id or API_ID,
            account.api_hash or API_HASH,
            account.phone,
            in_memory=True,
            proxy=config_manager.proxy if use_proxy else None,
            workdir=str(config_manager.basedir),
        )

        client = Client(**client_params)
        try:
            await asyncio.wait_for(client.start(), timeout=30)
        except asyncio.TimeoutError:
            return {"success": False, "message": "连接 Telegram 服务器超时，请检查网络或代理配置。"}
        except Exception as e:
            message = str(e) or e.__class__.__name__
            return {"success": False, "message": f"连接失败：{message}"}

        display_name = getattr(getattr(client, "me", None), "full_name", None) or account.phone
        try:
            await asyncio.wait_for(client.stop(), timeout=5)
        except Exception:
            pass
        return {"success": True, "message": f"连接成功，当前登录为「{display_name}」。"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to test telegram account: {e}")


@router.post("/telegram/accounts/test/code")
async def submit_telegram_test_code(
    login_id: str = Query(...),
    code: str = Query(...),
    kind: str = Query("code"),
    _: bool = Depends(require_auth),
):
    entry = _pending_logins.get(login_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="登录流程已过期，请重新测试")
    await entry["queue"].put({"kind": kind, "value": code})
    return {"success": True}


@router.get("/telegram/accounts/test/result")
async def get_telegram_test_result(login_id: str = Query(...), _: bool = Depends(require_auth)):
    entry = _pending_logins.get(login_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="登录流程已过期，请重新测试")
    result = {
        "state": entry.get("state"),
        "message": entry.get("message"),
        "success": bool(entry.get("success")),
        "session": entry.get("session"),
    }
    if entry.get("state") in {"done", "failed"}:
        _pending_logins.pop(login_id, None)
    return result


@router.delete("/telegram/accounts/{phone}")
async def delete_telegram_account(phone: str, _: bool = Depends(require_auth)):
    try:
        model, raw, accounts = _load_telegram_accounts()
        next_accounts = [account for account in accounts if account.phone != phone]

        if len(next_accounts) == len(accounts):
            raise HTTPException(status_code=404, detail="Telegram account not found")

        merged = _replace_accounts(raw, next_accounts)
        validated = Config(**merged)
        _write_config_dict(validated.model_dump(mode="json", exclude_none=True, exclude_unset=True))
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
