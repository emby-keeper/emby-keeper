import asyncio
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import APIRouter, HTTPException
import tomli as tomllib

import tomlkit
from pydantic import BaseModel, Field, ValidationError

from ..config import config as config_manager
from ..schema import Config as CoreConfig, format_errors
from ..utils import deep_update

router = APIRouter()


class ProxySettingsPayload(BaseModel):
    enabled: bool = False
    scheme: str = Field("http", pattern="^(socks5|http)$")
    hostname: str = "127.0.0.1"
    port: Optional[int] = Field(7890, gt=0)
    username: str = ""
    password: str = ""


class SystemSettingsPayload(BaseModel):
    nofail: bool = True
    debug_cron: bool = False
    notifier_enabled: bool = False
    notifier_account: str = "1"
    notifier_immediately: bool = False
    notifier_once: bool = False
    notifier_method: str = Field("telegram", pattern="^(telegram|apprise)$")
    notifier_apprise_uri: str = ""
    checkiner_enabled: bool = True
    checkiner_time_range: str = "<11:00AM,11:00PM>"
    checkiner_interval_days: str = "1"
    checkiner_timeout: int = Field(120, gt=0)
    checkiner_retries: int = Field(4, ge=0)
    checkiner_concurrency: int = Field(1, gt=0)
    checkiner_random_start: int = Field(60, ge=0)
    emby_enabled: bool = True
    emby_time_range: str = "<11:00AM,11:00PM>"
    emby_interval_days: str = "<7,12>"
    emby_concurrency: int = Field(1, gt=0)
    subsonic_enabled: bool = True
    subsonic_time_range: str = "<11:00AM,11:00PM>"
    subsonic_interval_days: str = "<7,12>"
    subsonic_concurrency: int = Field(1, gt=0)
    registrar_enabled: bool = True
    registrar_concurrency: int = Field(1, gt=0)
    telegram_use_proxy: bool = True
    proxy: ProxySettingsPayload = Field(default_factory=ProxySettingsPayload)


class BasicSettingsPayload(BaseModel):
    nofail: bool = True
    debug_cron: bool = False


class NotifierSettingsPayload(BaseModel):
    notifier_enabled: bool = False
    notifier_account: str = "1"
    notifier_immediately: bool = False
    notifier_once: bool = False
    notifier_method: str = Field("telegram", pattern="^(telegram|apprise)$")
    notifier_apprise_uri: str = ""


class SchedulerSettingsPayload(BaseModel):
    checkiner_enabled: bool = True
    checkiner_time_range: str = "<11:00AM,11:00PM>"
    checkiner_interval_days: str = "1"
    checkiner_timeout: int = Field(120, gt=0)
    checkiner_retries: int = Field(4, ge=0)
    checkiner_concurrency: int = Field(1, gt=0)
    checkiner_random_start: int = Field(60, ge=0)
    emby_enabled: bool = True
    emby_time_range: str = "<11:00AM,11:00PM>"
    emby_interval_days: str = "<7,12>"
    emby_concurrency: int = Field(1, gt=0)
    subsonic_enabled: bool = True
    subsonic_time_range: str = "<11:00AM,11:00PM>"
    subsonic_interval_days: str = "<7,12>"
    subsonic_concurrency: int = Field(1, gt=0)
    registrar_enabled: bool = True
    registrar_concurrency: int = Field(1, gt=0)
    site_checkiner: Optional[List[str]] = None
    site_monitor: Optional[List[str]] = None
    site_messager: Optional[List[str]] = None
    site_registrar: Optional[List[str]] = None


class NetworkSettingsPayload(BaseModel):
    telegram_use_proxy: bool = True
    proxy: ProxySettingsPayload = Field(default_factory=ProxySettingsPayload)


def _load_model() -> CoreConfig:
    raw = _read_config_dict()
    return CoreConfig(**raw)


def _serialize_system_settings(model: CoreConfig) -> Dict[str, Any]:
    notifier_account = model.notifier.account if model.notifier and model.notifier.account is not None else 1

    proxy_enabled = bool(model.proxy and model.proxy.hostname and model.proxy.port)

    return SystemSettingsPayload(
        nofail=bool(model.nofail),
        debug_cron=bool(model.debug_cron),
        notifier_enabled=bool(model.notifier.enabled) if model.notifier else False,
        notifier_account=str(notifier_account),
        notifier_immediately=bool(model.notifier.immediately) if model.notifier else False,
        notifier_once=bool(model.notifier.once) if model.notifier else False,
        notifier_method=(model.notifier.method if model.notifier and model.notifier.method else "telegram"),
        notifier_apprise_uri=(
            model.notifier.apprise_uri if model.notifier and model.notifier.apprise_uri else ""
        ),
        checkiner_enabled=(
            bool(model.checkiner.enabled) if model.checkiner and model.checkiner.enabled is not None else True
        ),
        checkiner_time_range=(
            model.checkiner.time_range
            if model.checkiner and model.checkiner.time_range
            else "<11:00AM,11:00PM>"
        ),
        checkiner_interval_days=(
            str(model.checkiner.interval_days)
            if model.checkiner and model.checkiner.interval_days is not None
            else "1"
        ),
        checkiner_timeout=(
            model.checkiner.timeout if model.checkiner and model.checkiner.timeout is not None else 120
        ),
        checkiner_retries=(
            model.checkiner.retries if model.checkiner and model.checkiner.retries is not None else 4
        ),
        checkiner_concurrency=(
            model.checkiner.concurrency if model.checkiner and model.checkiner.concurrency is not None else 1
        ),
        checkiner_random_start=(
            model.checkiner.random_start
            if model.checkiner and model.checkiner.random_start is not None
            else 60
        ),
        emby_enabled=bool(model.emby.enabled) if model.emby and model.emby.enabled is not None else True,
        emby_time_range=(
            model.emby.time_range if model.emby and model.emby.time_range else "<11:00AM,11:00PM>"
        ),
        emby_interval_days=(
            str(model.emby.interval_days) if model.emby and model.emby.interval_days is not None else "<7,12>"
        ),
        emby_concurrency=model.emby.concurrency if model.emby and model.emby.concurrency is not None else 1,
        subsonic_enabled=(
            bool(model.subsonic.enabled) if model.subsonic and model.subsonic.enabled is not None else True
        ),
        subsonic_time_range=(
            model.subsonic.time_range if model.subsonic and model.subsonic.time_range else "<11:00AM,11:00PM>"
        ),
        subsonic_interval_days=(
            str(model.subsonic.interval_days)
            if model.subsonic and model.subsonic.interval_days is not None
            else "<7,12>"
        ),
        subsonic_concurrency=(
            model.subsonic.concurrency if model.subsonic and model.subsonic.concurrency is not None else 1
        ),
        registrar_enabled=(
            bool(model.registrar.enabled) if model.registrar and model.registrar.enabled is not None else True
        ),
        registrar_concurrency=(
            model.registrar.concurrency if model.registrar and model.registrar.concurrency is not None else 1
        ),
        telegram_use_proxy=bool(model.telegram.use_proxy) if model.telegram else True,
        proxy=ProxySettingsPayload(
            enabled=proxy_enabled,
            scheme=model.proxy.scheme if proxy_enabled and model.proxy and model.proxy.scheme else "http",
            hostname=(
                model.proxy.hostname
                if proxy_enabled and model.proxy and model.proxy.hostname
                else "127.0.0.1"
            ),
            port=model.proxy.port if proxy_enabled and model.proxy else 7890,
            username=model.proxy.username if proxy_enabled and model.proxy and model.proxy.username else "",
            password=model.proxy.password if proxy_enabled and model.proxy and model.proxy.password else "",
        ),
    ).model_dump()


def _build_system_update(payload: SystemSettingsPayload) -> Dict[str, Any]:
    notifier_account: Any = payload.notifier_account
    if notifier_account.isdigit():
        notifier_account = int(notifier_account)

    proxy_value: Optional[Dict[str, Any]] = None
    if payload.proxy.enabled:
        proxy_value = {
            "scheme": payload.proxy.scheme,
            "hostname": payload.proxy.hostname,
            "port": payload.proxy.port,
        }
        if payload.proxy.username:
            proxy_value["username"] = payload.proxy.username
        if payload.proxy.password:
            proxy_value["password"] = payload.proxy.password

    return {
        "nofail": payload.nofail,
        "debug_cron": payload.debug_cron,
        "notifier": {
            "enabled": payload.notifier_enabled,
            "account": notifier_account,
            "immediately": payload.notifier_immediately,
            "once": payload.notifier_once,
            "method": payload.notifier_method,
            "apprise_uri": payload.notifier_apprise_uri or None,
        },
        "checkiner": {
            "enabled": payload.checkiner_enabled,
            "time_range": payload.checkiner_time_range,
            "interval_days": payload.checkiner_interval_days,
            "timeout": payload.checkiner_timeout,
            "retries": payload.checkiner_retries,
            "concurrency": payload.checkiner_concurrency,
            "random_start": payload.checkiner_random_start,
        },
        "emby": {
            "enabled": payload.emby_enabled,
            "time_range": payload.emby_time_range,
            "interval_days": payload.emby_interval_days,
            "concurrency": payload.emby_concurrency,
        },
        "subsonic": {
            "enabled": payload.subsonic_enabled,
            "time_range": payload.subsonic_time_range,
            "interval_days": payload.subsonic_interval_days,
            "concurrency": payload.subsonic_concurrency,
        },
        "registrar": {
            "enabled": payload.registrar_enabled,
            "concurrency": payload.registrar_concurrency,
        },
        "telegram": {
            "use_proxy": payload.telegram_use_proxy,
        },
        "proxy": proxy_value,
    }


def _serialize_basic_settings(model: CoreConfig) -> Dict[str, Any]:
    return BasicSettingsPayload(
        nofail=bool(model.nofail),
        debug_cron=bool(model.debug_cron),
    ).model_dump()


def _serialize_notifier_settings(model: CoreConfig) -> Dict[str, Any]:
    notifier_account = model.notifier.account if model.notifier and model.notifier.account is not None else 1
    return NotifierSettingsPayload(
        notifier_enabled=bool(model.notifier.enabled) if model.notifier else False,
        notifier_account=str(notifier_account),
        notifier_immediately=bool(model.notifier.immediately) if model.notifier else False,
        notifier_once=bool(model.notifier.once) if model.notifier else False,
        notifier_method=(model.notifier.method if model.notifier and model.notifier.method else "telegram"),
        notifier_apprise_uri=(
            model.notifier.apprise_uri if model.notifier and model.notifier.apprise_uri else ""
        ),
    ).model_dump()


def _serialize_scheduler_settings(model: CoreConfig) -> Dict[str, Any]:
    return SchedulerSettingsPayload(
        checkiner_enabled=(
            bool(model.checkiner.enabled) if model.checkiner and model.checkiner.enabled is not None else True
        ),
        checkiner_time_range=(
            model.checkiner.time_range
            if model.checkiner and model.checkiner.time_range
            else "<11:00AM,11:00PM>"
        ),
        checkiner_interval_days=(
            str(model.checkiner.interval_days)
            if model.checkiner and model.checkiner.interval_days is not None
            else "1"
        ),
        checkiner_timeout=(
            model.checkiner.timeout if model.checkiner and model.checkiner.timeout is not None else 120
        ),
        checkiner_retries=(
            model.checkiner.retries if model.checkiner and model.checkiner.retries is not None else 4
        ),
        checkiner_concurrency=(
            model.checkiner.concurrency if model.checkiner and model.checkiner.concurrency is not None else 1
        ),
        checkiner_random_start=(
            model.checkiner.random_start
            if model.checkiner and model.checkiner.random_start is not None
            else 60
        ),
        emby_enabled=bool(model.emby.enabled) if model.emby and model.emby.enabled is not None else True,
        emby_time_range=(
            model.emby.time_range if model.emby and model.emby.time_range else "<11:00AM,11:00PM>"
        ),
        emby_interval_days=(
            str(model.emby.interval_days) if model.emby and model.emby.interval_days is not None else "<7,12>"
        ),
        emby_concurrency=model.emby.concurrency if model.emby and model.emby.concurrency is not None else 1,
        subsonic_enabled=(
            bool(model.subsonic.enabled) if model.subsonic and model.subsonic.enabled is not None else True
        ),
        subsonic_time_range=(
            model.subsonic.time_range if model.subsonic and model.subsonic.time_range else "<11:00AM,11:00PM>"
        ),
        subsonic_interval_days=(
            str(model.subsonic.interval_days)
            if model.subsonic and model.subsonic.interval_days is not None
            else "<7,12>"
        ),
        subsonic_concurrency=(
            model.subsonic.concurrency if model.subsonic and model.subsonic.concurrency is not None else 1
        ),
        registrar_enabled=(
            bool(model.registrar.enabled) if model.registrar and model.registrar.enabled is not None else True
        ),
        registrar_concurrency=(
            model.registrar.concurrency if model.registrar and model.registrar.concurrency is not None else 1
        ),
        site_checkiner=model.site.checkiner if model.site else None,
        site_monitor=model.site.monitor if model.site else None,
        site_messager=model.site.messager if model.site else None,
        site_registrar=model.site.registrar if model.site else None,
    ).model_dump()


def _serialize_network_settings(model: CoreConfig) -> Dict[str, Any]:
    proxy_enabled = bool(model.proxy and model.proxy.hostname and model.proxy.port)
    return NetworkSettingsPayload(
        telegram_use_proxy=bool(model.telegram.use_proxy) if model.telegram else True,
        proxy=ProxySettingsPayload(
            enabled=proxy_enabled,
            scheme=model.proxy.scheme if proxy_enabled and model.proxy and model.proxy.scheme else "http",
            hostname=(
                model.proxy.hostname
                if proxy_enabled and model.proxy and model.proxy.hostname
                else "127.0.0.1"
            ),
            port=model.proxy.port if proxy_enabled and model.proxy else 7890,
            username=model.proxy.username if proxy_enabled and model.proxy and model.proxy.username else "",
            password=model.proxy.password if proxy_enabled and model.proxy and model.proxy.password else "",
        ),
    ).model_dump()


def _build_basic_update(payload: BasicSettingsPayload) -> Dict[str, Any]:
    return {
        "nofail": payload.nofail,
        "debug_cron": payload.debug_cron,
    }


def _build_notifier_update(payload: NotifierSettingsPayload) -> Dict[str, Any]:
    notifier_account: Any = payload.notifier_account
    if notifier_account.isdigit():
        notifier_account = int(notifier_account)
    return {
        "notifier": {
            "enabled": payload.notifier_enabled,
            "account": notifier_account,
            "immediately": payload.notifier_immediately,
            "once": payload.notifier_once,
            "method": payload.notifier_method,
            "apprise_uri": payload.notifier_apprise_uri or None,
        }
    }


def _build_scheduler_update(payload: SchedulerSettingsPayload) -> Dict[str, Any]:
    return {
        "checkiner": {
            "enabled": payload.checkiner_enabled,
            "time_range": payload.checkiner_time_range,
            "interval_days": payload.checkiner_interval_days,
            "timeout": payload.checkiner_timeout,
            "retries": payload.checkiner_retries,
            "concurrency": payload.checkiner_concurrency,
            "random_start": payload.checkiner_random_start,
        },
        "emby": {
            "enabled": payload.emby_enabled,
            "time_range": payload.emby_time_range,
            "interval_days": payload.emby_interval_days,
            "concurrency": payload.emby_concurrency,
        },
        "subsonic": {
            "enabled": payload.subsonic_enabled,
            "time_range": payload.subsonic_time_range,
            "interval_days": payload.subsonic_interval_days,
            "concurrency": payload.subsonic_concurrency,
        },
        "registrar": {
            "enabled": payload.registrar_enabled,
            "concurrency": payload.registrar_concurrency,
        },
        "site": {
            "checkiner": payload.site_checkiner,
            "monitor": payload.site_monitor,
            "messager": payload.site_messager,
            "registrar": payload.site_registrar,
        },
    }


def _build_network_update(payload: NetworkSettingsPayload) -> Dict[str, Any]:
    proxy_value: Optional[Dict[str, Any]] = None
    if payload.proxy.enabled:
        proxy_value = {
            "scheme": payload.proxy.scheme,
            "hostname": payload.proxy.hostname,
            "port": payload.proxy.port,
        }
        if payload.proxy.username:
            proxy_value["username"] = payload.proxy.username
        if payload.proxy.password:
            proxy_value["password"] = payload.proxy.password
    return {
        "telegram": {
            "use_proxy": payload.telegram_use_proxy,
        },
        "proxy": proxy_value,
    }


def _save_partial_settings(update: Dict[str, Any], *, drop_proxy: bool = False, drop_site: bool = False):
    current = _read_config_dict()
    merged = deep_update(current, update)
    if drop_proxy:
        merged.pop("proxy", None)
    if drop_site:
        merged.pop("site", None)
    model = CoreConfig(**merged)
    minimal = model.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    _write_config_dict(minimal)
    return {"success": True}


def _active_config_file():
    conf_file = getattr(config_manager, "_conf_file", None)
    if conf_file:
        return Path(conf_file)
    return config_manager.basedir / "config.toml"


def _config_path():
    return _active_config_file()


def _read_config_dict() -> Dict[str, Any]:
    cfg_file = _config_path()
    if not cfg_file.exists():
        return {}
    with open(cfg_file, "rb") as f:
        return tomllib.load(f)


def _write_config_dict(cfg: Dict[str, Any]):
    cfg_file = _config_path()
    with open(cfg_file, "w", encoding="utf-8") as f:
        f.write(tomlkit.dumps(cfg))
    # 写盘后强制同步 config_manager 内存（watchdog awatch 不总是触发 reload）
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(config_manager.reload_conf(_active_config_file()))
    except RuntimeError:
        pass


@router.get("/config")
async def get_config():
    try:
        raw = _read_config_dict()
        model = CoreConfig(**raw)
        return model.model_dump()
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载配置失败: {e}")


@router.post("/config")
async def save_config(payload: Dict[str, Any]):
    try:
        model = CoreConfig(**payload)
        # Persist only explicitly provided fields to avoid injecting defaults from API layer
        minimal = model.model_dump(mode="json", exclude_none=True, exclude_unset=True)
        _write_config_dict(minimal)
        return {"success": True}
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存配置失败: {e}")


@router.get("/settings")
async def get_system_settings():
    try:
        model = _load_model()
        return _serialize_system_settings(model)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载系统设置失败: {e}")


@router.post("/settings")
async def save_system_settings(payload: SystemSettingsPayload):
    try:
        current = _read_config_dict()
        update = _build_system_update(payload)
        merged = deep_update(current, update)
        if not payload.proxy.enabled:
            merged.pop("proxy", None)

        model = CoreConfig(**merged)
        minimal = model.model_dump(mode="json", exclude_none=True, exclude_unset=True)
        _write_config_dict(minimal)
        return {"success": True}
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存系统设置失败: {e}")


@router.get("/settings/basic")
async def get_basic_settings():
    try:
        return _serialize_basic_settings(_load_model())
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载基础设置失败: {e}")


@router.post("/settings/basic")
async def save_basic_settings(payload: BasicSettingsPayload):
    try:
        return _save_partial_settings(_build_basic_update(payload))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存基础设置失败: {e}")


@router.get("/settings/notifier")
async def get_notifier_settings():
    try:
        return _serialize_notifier_settings(_load_model())
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载通知设置失败: {e}")


@router.post("/settings/notifier")
async def save_notifier_settings(payload: NotifierSettingsPayload):
    try:
        return _save_partial_settings(_build_notifier_update(payload))
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存通知设置失败: {e}")


@router.get("/settings/scheduler")
async def get_scheduler_settings():
    try:
        return _serialize_scheduler_settings(_load_model())
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载调度设置失败: {e}")


@router.post("/settings/scheduler")
async def save_scheduler_settings(payload: SchedulerSettingsPayload):
    try:
        drop_site = all(
            value is None
            for value in [
                payload.site_checkiner,
                payload.site_monitor,
                payload.site_messager,
                payload.site_registrar,
            ]
        )
        return _save_partial_settings(_build_scheduler_update(payload), drop_site=drop_site)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存调度设置失败: {e}")


@router.get("/settings/network")
async def get_network_settings():
    try:
        return _serialize_network_settings(_load_model())
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载网络设置失败: {e}")


@router.post("/settings/network")
async def save_network_settings(payload: NetworkSettingsPayload):
    try:
        return _save_partial_settings(_build_network_update(payload), drop_proxy=not payload.proxy.enabled)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存网络设置失败: {e}")
