"""Operational overview APIs for user-facing daily status."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query

from .auth import require_auth
from .config import _read_config_dict
from .runinfo import _sort_datetime
from .telegram import _infer_checkin_outcome, _get_last_checkin_status
from ..cache import cache
from ..config import config as config_manager
from ..runinfo import RunContext, RunStatus
from ..schema import Config, EmbyAccount, SubsonicAccount, TelegramAccount

router = APIRouter()


def _load_config() -> Config:
    return Config(**_read_config_dict())


def _parse_day(day: Optional[str]) -> datetime:
    now = datetime.now(timezone.utc).astimezone()
    if not day:
        return now.replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        parsed = datetime.strptime(day, "%Y-%m-%d")
        return parsed.replace(tzinfo=now.tzinfo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid day format, expected YYYY-MM-DD") from exc


def _ctx_time(ctx: RunContext) -> datetime:
    return _sort_datetime(ctx.end_time or ctx.start_time)


def _in_day(ctx: RunContext, start: datetime, end: datetime) -> bool:
    stamp = _ctx_time(ctx)
    return start <= stamp < end


def _is_terminal(ctx: RunContext) -> bool:
    return ctx.status not in {
        RunStatus.PENDING,
        RunStatus.INITIALIZING,
        RunStatus.RUNNING,
        RunStatus.CATAGORY,
    }


def _history_records(prefix: str, account_host: str, username: str) -> List[Dict[str, str]]:
    key = f"{prefix}.{account_host}.{username}"
    raw = cache.get(key, []) or []
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
    return records


def _status_from_history(
    records: List[Dict[str, str]], day_start: datetime, day_end: datetime, is_today: bool
):
    day_hits = []
    for record in records:
        try:
            stamp = datetime.fromisoformat(record["time"])
        except ValueError:
            continue
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        stamp = stamp.astimezone(day_start.tzinfo)
        if day_start <= stamp < day_end:
            day_hits.append((stamp, record["status"]))
    if day_hits:
        day_hits.sort(key=lambda item: item[0], reverse=True)
        stamp, status = day_hits[0]
        return status, stamp.isoformat(), None
    if records and is_today:
        latest = records[0]
        return f"last_{latest['status']}", latest["time"], "今日尚未执行，显示最近一次结果"
    if records:
        latest = records[0]
        try:
            stamp = datetime.fromisoformat(latest["time"])
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            if day_start <= stamp.astimezone(day_start.tzinfo) < day_end:
                return latest["status"], latest["time"], None
        except ValueError:
            pass
    return None, None, None


def _build_recent_days(all_contexts, cfg, days: int = 14) -> List[Dict[str, Any]]:
    """Build a compact recent-day strip for quick scanning."""
    now = datetime.now().astimezone()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    telegram_accounts = list(cfg.telegram.account or []) if cfg.telegram else []
    emby_accounts = list(cfg.emby.account or []) if cfg.emby else []
    subsonic_accounts = list(cfg.subsonic.account or []) if cfg.subsonic else []
    checkiner_enabled = (
        bool(cfg.checkiner.enabled) if cfg.checkiner and cfg.checkiner.enabled is not None else True
    )
    emby_enabled = bool(cfg.emby.enabled) if cfg.emby and cfg.emby.enabled is not None else True
    subsonic_enabled = (
        bool(cfg.subsonic.enabled) if cfg.subsonic and cfg.subsonic.enabled is not None else True
    )

    recent = []
    for offset in range(days):
        day_start = today - timedelta(days=offset)
        day_end = day_start + timedelta(days=1)
        attention = 0
        success = 0
        total = 0

        if checkiner_enabled:
            for account in telegram_accounts:
                if not (account.enabled and account.checkiner):
                    continue
                total += 1
                target = f"{account.phone} 账号签到"
                day_runs = [
                    ctx
                    for ctx in all_contexts
                    if ctx.description == target and _in_day(ctx, day_start, day_end) and _is_terminal(ctx)
                ]
                day_runs.sort(key=_ctx_time, reverse=True)
                outcome = _infer_checkin_outcome(day_runs[0]) if day_runs else None
                if outcome in {"failed", "partial_failed"}:
                    attention += 1
                elif outcome == "success":
                    success += 1

        if emby_enabled:
            for account in emby_accounts:
                if not account.enabled:
                    continue
                total += 1
                host = account.url.host
                records = _history_records("emby.account_history", host, account.username)
                status, _, _ = _status_from_history(records, day_start, day_end, False)
                if status == "failed":
                    attention += 1
                elif status == "success":
                    success += 1

        if subsonic_enabled:
            for account in subsonic_accounts:
                if not account.enabled:
                    continue
                total += 1
                host = getattr(account.url, "host", None) or str(account.url)
                records = _history_records("subsonic.account_history", str(host), account.username)
                status, _, _ = _status_from_history(records, day_start, day_end, False)
                if status == "failed":
                    attention += 1
                elif status == "success":
                    success += 1

        if attention > 0:
            state = "attention"
        elif success > 0 and success >= max(1, total // 2):
            state = "ok"
        elif success > 0:
            state = "mixed"
        else:
            state = "unknown"

        label = "今天" if offset == 0 else ("昨天" if offset == 1 else day_start.strftime("%m-%d"))
        recent.append(
            {
                "day": day_start.strftime("%Y-%m-%d"),
                "label": label,
                "state": state,
                "attention": attention,
                "success": success,
                "total": total,
            }
        )
    return recent


def _emby_spec(account: EmbyAccount) -> str:
    return f"{account.username}@{account.name or account.url.host}"


def _subsonic_spec(account: SubsonicAccount) -> str:
    host = getattr(account.url, "host", None) or str(account.url)
    return f"{account.username}@{account.name or host}"


def _match_emby_account_run(ctx: RunContext, account: EmbyAccount) -> bool:
    spec = _emby_spec(account)
    descriptions = {
        f"Emby 保活任务 - {spec}",
        f"Emby 测试运行 - {spec}",
        "使用全局设置的 Emby 统一保活",
    }
    if ctx.description not in descriptions:
        return False
    if ctx.description != "使用全局设置的 Emby 统一保活":
        return True
    for log in ctx.yield_logs(reverse=True):
        message = str(log.message or "")
        if spec in message and ("保活成功" in message or "保活失败" in message):
            return True
    return False


def _match_subsonic_account_run(ctx: RunContext, account: SubsonicAccount) -> bool:
    spec = _subsonic_spec(account)
    descriptions = {
        f"Subsonic 保活任务 - {spec}",
        "使用全局设置的 Subsonic 统一保活",
    }
    if ctx.description not in descriptions:
        return False
    if ctx.description != "使用全局设置的 Subsonic 统一保活":
        return True
    for log in ctx.yield_logs(reverse=True):
        message = str(log.message or "")
        if spec in message and ("保活成功" in message or "保活失败" in message):
            return True
    return False


def _keepalive_outcome(ctx: RunContext, account_spec: str) -> Optional[str]:
    """Resolve keepalive result for one account from a run context."""
    description = ctx.description or ""
    dedicated = account_spec in description

    for log in reversed(list(ctx.yield_logs(include_children=False))):
        message = str(log.message or "")
        if account_spec not in message and not dedicated:
            continue
        if "保活失败" in message:
            return "failed"
        if "保活成功" in message:
            return "success"

    if dedicated:
        if ctx.status_info == "保活成功" or ctx.status == RunStatus.SUCCESS:
            return "success"
        if ctx.status_info == "保活失败" or ctx.status in {RunStatus.FAIL, RunStatus.ERROR}:
            return "failed"
    return None


def _latest_outcome_for_account(
    contexts: List[RunContext],
    matcher,
    outcome_fn,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    latest_status: Optional[str] = None
    latest_time: Optional[datetime] = None
    latest_info: Optional[str] = None

    for ctx in contexts:
        if not matcher(ctx):
            continue
        if not _is_terminal(ctx):
            continue
        status = outcome_fn(ctx)
        if not status:
            continue
        stamp = _ctx_time(ctx)
        if latest_time is None or stamp > latest_time:
            latest_status = status
            latest_time = stamp
            latest_info = ctx.status_info or ctx.description

    return (
        latest_status,
        latest_time.isoformat() if latest_time else None,
        latest_info,
    )


def _scan_attention_events(
    contexts: List[RunContext], start: datetime, end: datetime, limit: int = 12
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    keywords = (
        ("邀请码", "invite"),
        ("警告", "warning"),
        ("被限制", "warning"),
        ("FloodWait", "warning"),
        ("保活失败", "keepalive_fail"),
        ("签到失败", "checkin_fail"),
        ("签到部分失败", "checkin_partial"),
    )

    for ctx in contexts:
        for log in ctx.yield_logs(include_children=False):
            stamp = _sort_datetime(log.time)
            if not (start <= stamp < end):
                continue
            message = str(log.message or "")
            level = str(log.level or "INFO").upper()
            matched_kind = None
            for keyword, kind in keywords:
                if keyword in message:
                    matched_kind = kind
                    break
            if matched_kind is None and level in {"ERROR", "WARNING"}:
                matched_kind = "error" if level == "ERROR" else "warning"
            if matched_kind is None:
                continue

            description = str(ctx.description or "")
            description_lower = description.lower()
            if matched_kind == "invite" or "监控" in description:
                module_key = "monitor"
            elif "水群" in description or "messager" in description_lower:
                module_key = "messager"
            elif "subsonic" in description_lower:
                module_key = "subsonic"
            elif "emby" in description_lower or (
                "保活" in description and "subsonic" not in description_lower
            ):
                module_key = "emby"
            elif matched_kind in {"checkin_fail", "checkin_partial"} or "签到" in description:
                module_key = "checkin"
            elif matched_kind == "keepalive_fail":
                module_key = "emby"
            else:
                module_key = "checkin"

            events.append(
                {
                    "kind": matched_kind,
                    "moduleKey": module_key,
                    "level": level,
                    "message": message,
                    "time": stamp.isoformat(),
                    "run_id": ctx.id,
                    "description": ctx.description,
                }
            )

    events.sort(key=lambda item: item["time"] or "", reverse=True)
    return events[:limit]


def _build_module_card(
    key: str,
    title: str,
    enabled: bool,
    total: int,
    success: int,
    attention: int,
    pending: int,
    unknown: int,
    items: List[Dict[str, Any]],
    empty_hint: str,
) -> Dict[str, Any]:
    if not enabled:
        state = "disabled"
        summary = "未启用"
    elif total == 0:
        state = "empty"
        summary = empty_hint
    elif attention > 0:
        state = "attention"
        summary = f"{attention} 个需要关注"
    elif pending > 0:
        state = "pending"
        summary = f"{pending} 个进行中"
    elif success == total:
        state = "ok"
        summary = "全部正常"
    elif unknown == total:
        state = "unknown"
        summary = "暂无今日结果"
    else:
        state = "mixed"
        summary = f"{success}/{total} 正常"

    return {
        "key": key,
        "title": title,
        "enabled": enabled,
        "state": state,
        "summary": summary,
        "counts": {
            "total": total,
            "success": success,
            "attention": attention,
            "pending": pending,
            "unknown": unknown,
        },
        "items": items,
    }


@router.get("/ops/overview")
async def get_ops_overview(
    day: Optional[str] = Query(None, description="Local calendar day YYYY-MM-DD"),
    _: bool = Depends(require_auth),
):
    try:
        day_start = _parse_day(day)
        day_end = day_start + timedelta(days=1)
        day_label = day_start.strftime("%Y-%m-%d")
        is_today = day_start.date() == datetime.now().astimezone().date()

        cfg = _load_config()
        all_contexts = RunContext.list_all()

        telegram_accounts = list(cfg.telegram.account or []) if cfg.telegram else []
        emby_accounts = list(cfg.emby.account or []) if cfg.emby else []
        subsonic_accounts = list(cfg.subsonic.account or []) if cfg.subsonic else []

        checkiner_enabled = (
            bool(cfg.checkiner.enabled) if cfg.checkiner and cfg.checkiner.enabled is not None else True
        )
        monitor_enabled = (
            bool(cfg.monitor.enabled) if cfg.monitor and cfg.monitor.enabled is not None else True
        )
        messager_enabled = (
            bool(cfg.messager.enabled) if cfg.messager and cfg.messager.enabled is not None else True
        )
        emby_enabled = bool(cfg.emby.enabled) if cfg.emby and cfg.emby.enabled is not None else True
        subsonic_enabled = (
            bool(cfg.subsonic.enabled) if cfg.subsonic and cfg.subsonic.enabled is not None else True
        )

        # --- Checkin ---
        checkin_items: List[Dict[str, Any]] = []
        checkin_accounts = [account for account in telegram_accounts if account.enabled and account.checkiner]
        for account in checkin_accounts:
            target = f"{account.phone} 账号签到"
            day_runs = [
                ctx for ctx in all_contexts if ctx.description == target and _in_day(ctx, day_start, day_end)
            ]
            day_runs.sort(key=_ctx_time, reverse=True)

            status = None
            status_time = None
            status_info = None
            for ctx in day_runs:
                if not _is_terminal(ctx):
                    if status is None:
                        status = "running"
                        status_time = _ctx_time(ctx).isoformat()
                        status_info = "签到进行中"
                    continue
                outcome = _infer_checkin_outcome(ctx)
                if outcome:
                    status = outcome
                    status_time = _ctx_time(ctx).isoformat()
                    status_info = ctx.status_info
                    break

            if status is None and is_today:
                # Fall back to last known result if nothing happened today yet.
                last_status, last_time = _get_last_checkin_status(account.phone)
                if last_status and last_time:
                    last_dt = datetime.fromisoformat(last_time)
                    if last_dt.tzinfo is None:
                        last_dt = last_dt.replace(tzinfo=timezone.utc)
                    # Only show as "上次结果" when not today.
                    if not (day_start <= last_dt.astimezone(day_start.tzinfo) < day_end):
                        status = f"last_{last_status}"
                        status_time = last_time
                        status_info = "今日尚未执行，显示最近一次结果"

            if status is None:
                status = "unknown"

            checkin_items.append(
                {
                    "id": account.phone,
                    "label": TelegramAccount.get_phone_masked(account.phone),
                    "status": status,
                    "time": status_time,
                    "detail": status_info,
                }
            )

        def _count_status(items: List[Dict[str, Any]], *names: str) -> int:
            return sum(1 for item in items if item["status"] in names)

        checkin_card = _build_module_card(
            key="checkin",
            title="签到",
            enabled=checkiner_enabled,
            total=len(checkin_items),
            success=_count_status(checkin_items, "success", "last_success"),
            attention=_count_status(
                checkin_items, "failed", "partial_failed", "last_failed", "last_partial_failed"
            ),
            pending=_count_status(checkin_items, "running"),
            unknown=_count_status(checkin_items, "unknown"),
            items=checkin_items,
            empty_hint="没有启用签到的账号",
        )

        # --- Emby keepalive ---
        emby_items: List[Dict[str, Any]] = []
        active_emby = [account for account in emby_accounts if account.enabled]
        for account in active_emby:
            spec = _emby_spec(account)
            history = _history_records("emby.account_history", account.url.host, account.username)
            status, status_time, detail = _status_from_history(history, day_start, day_end, is_today)
            matched = [ctx for ctx in all_contexts if _match_emby_account_run(ctx, account)]
            day_matched = [ctx for ctx in matched if _in_day(ctx, day_start, day_end)]
            day_matched.sort(key=_ctx_time, reverse=True)

            if status is None:
                for ctx in day_matched:
                    if not _is_terminal(ctx):
                        status = "running"
                        status_time = _ctx_time(ctx).isoformat()
                        detail = "保活进行中"
                        break
                    outcome = _keepalive_outcome(ctx, spec)
                    if outcome:
                        status = outcome
                        status_time = _ctx_time(ctx).isoformat()
                        detail = ctx.status_info
                        break

            if status is None:
                # Fallback to most recent history outside the day.
                latest_status, latest_time, latest_info = _latest_outcome_for_account(
                    matched,
                    lambda ctx, account=account: _match_emby_account_run(ctx, account),
                    lambda ctx, spec=spec: _keepalive_outcome(ctx, spec),
                )
                if latest_status and is_today:
                    status = f"last_{latest_status}"
                    status_time = latest_time
                    detail = "今日尚未执行，显示最近一次结果"
                elif latest_status:
                    status = latest_status
                    status_time = latest_time
                    detail = latest_info
                else:
                    status = "unknown"

            emby_items.append(
                {
                    "id": spec,
                    "label": account.name or account.username,
                    "subtitle": account.url.host if hasattr(account.url, "host") else str(account.url),
                    "status": status,
                    "time": status_time,
                    "detail": detail,
                }
            )

        emby_card = _build_module_card(
            key="emby",
            title="Emby 保活",
            enabled=emby_enabled,
            total=len(emby_items),
            success=_count_status(emby_items, "success", "last_success"),
            attention=_count_status(emby_items, "failed", "last_failed"),
            pending=_count_status(emby_items, "running"),
            unknown=_count_status(emby_items, "unknown"),
            items=emby_items,
            empty_hint="没有启用的 Emby 账号",
        )

        # --- Subsonic keepalive ---
        subsonic_items: List[Dict[str, Any]] = []
        active_subsonic = [account for account in subsonic_accounts if account.enabled]
        for account in active_subsonic:
            spec = _subsonic_spec(account)
            host = getattr(account.url, "host", None) or str(account.url)
            history = _history_records("subsonic.account_history", str(host), account.username)
            status, status_time, detail = _status_from_history(history, day_start, day_end, is_today)
            matched = [ctx for ctx in all_contexts if _match_subsonic_account_run(ctx, account)]
            day_matched = [ctx for ctx in matched if _in_day(ctx, day_start, day_end)]
            day_matched.sort(key=_ctx_time, reverse=True)

            if status is None:
                for ctx in day_matched:
                    if not _is_terminal(ctx):
                        status = "running"
                        status_time = _ctx_time(ctx).isoformat()
                        detail = "保活进行中"
                        break
                    outcome = _keepalive_outcome(ctx, spec)
                    if outcome:
                        status = outcome
                        status_time = _ctx_time(ctx).isoformat()
                        detail = ctx.status_info
                        break

            if status is None:
                latest_status, latest_time, latest_info = _latest_outcome_for_account(
                    matched,
                    lambda ctx, account=account: _match_subsonic_account_run(ctx, account),
                    lambda ctx, spec=spec: _keepalive_outcome(ctx, spec),
                )
                if latest_status and is_today:
                    status = f"last_{latest_status}"
                    status_time = latest_time
                    detail = "今日尚未执行，显示最近一次结果"
                elif latest_status:
                    status = latest_status
                    status_time = latest_time
                    detail = latest_info
                else:
                    status = "unknown"

            subsonic_items.append(
                {
                    "id": spec,
                    "label": account.name or account.username,
                    "subtitle": host,
                    "status": status,
                    "time": status_time,
                    "detail": detail,
                }
            )

        subsonic_card = _build_module_card(
            key="subsonic",
            title="Subsonic 保活",
            enabled=subsonic_enabled,
            total=len(subsonic_items),
            success=_count_status(subsonic_items, "success", "last_success"),
            attention=_count_status(subsonic_items, "failed", "last_failed"),
            pending=_count_status(subsonic_items, "running"),
            unknown=_count_status(subsonic_items, "unknown"),
            items=subsonic_items,
            empty_hint="没有启用的 Subsonic 账号",
        )

        # --- Monitor / Messager attention (log-based, best effort) ---
        attention_events = _scan_attention_events(all_contexts, day_start, day_end)
        recent_days = _build_recent_days(all_contexts, cfg, days=14)
        invite_events = [event for event in attention_events if event["kind"] == "invite"]
        warning_events = [event for event in attention_events if event["kind"] in {"warning", "error"}]

        monitor_accounts = [account for account in telegram_accounts if account.enabled and account.monitor]
        messager_accounts = [account for account in telegram_accounts if account.enabled and account.messager]

        monitor_card = {
            "key": "monitor",
            "title": "消息监控",
            "enabled": monitor_enabled,
            "state": (
                "disabled"
                if not monitor_enabled
                else (
                    "empty"
                    if not monitor_accounts
                    else "attention" if invite_events or warning_events else "ok"
                )
            ),
            "summary": (
                "未启用"
                if not monitor_enabled
                else (
                    "没有启用监控的账号"
                    if not monitor_accounts
                    else (
                        f"发现 {len(invite_events)} 条邀请相关记录"
                        if invite_events
                        else "暂无需要关注的监控事件"
                    )
                )
            ),
            "counts": {
                "total": len(monitor_accounts),
                "events": len(invite_events),
            },
            "items": invite_events[:8],
        }

        messager_card = {
            "key": "messager",
            "title": "自动水群",
            "enabled": messager_enabled,
            "state": (
                "disabled"
                if not messager_enabled
                else "empty" if not messager_accounts else "attention" if warning_events else "ok"
            ),
            "summary": (
                "未启用"
                if not messager_enabled
                else (
                    "没有启用水群的账号"
                    if not messager_accounts
                    else (f"{len(warning_events)} 条警告/错误" if warning_events else "暂无异常提示")
                )
            ),
            "counts": {
                "total": len(messager_accounts),
                "events": len(warning_events),
            },
            "items": warning_events[:8],
        }

        running = [
            {
                "id": ctx.id,
                "description": ctx.description,
                "status": ctx.status.name if ctx.status else None,
                "start_time": ctx.start_time.isoformat() if ctx.start_time else None,
            }
            for ctx in all_contexts
            if ctx.status in {RunStatus.PENDING, RunStatus.INITIALIZING, RunStatus.RUNNING}
        ]

        attention_total = (
            checkin_card["counts"]["attention"]
            + emby_card["counts"]["attention"]
            + subsonic_card["counts"]["attention"]
            + (1 if monitor_card["state"] == "attention" else 0)
            + (1 if messager_card["state"] == "attention" else 0)
        )

        if attention_total > 0:
            headline = f"有 {attention_total} 处需要关注"
            tone = "attention"
        elif any(card["state"] == "pending" for card in (checkin_card, emby_card, subsonic_card)):
            headline = "有任务正在进行"
            tone = "pending"
        elif any(card["state"] == "ok" for card in (checkin_card, emby_card, subsonic_card)):
            headline = "今天看起来正常"
            tone = "ok"
        else:
            headline = "还没有足够的今日结果"
            tone = "unknown"

        return {
            "day": day_label,
            "is_today": is_today,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "headline": headline,
            "tone": tone,
            "modules": {
                "checkin": checkin_card,
                "emby": emby_card,
                "subsonic": subsonic_card,
                "monitor": monitor_card,
                "messager": messager_card,
            },
            "running": running,
            "attention_events": attention_events,
            "recent_days": recent_days,
            "limitations": [
                "近 14 天状态条基于已保存的签到/保活结果；更早或缺失的数据会显示为暂无。",
                "邀请码与水群异常目前来自日志关键词，可能不完整。",
                "若某账号今日尚未执行，会尽量展示最近一次结果并标明。",
            ],
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build ops overview: {exc}") from exc


def _day_state_for_calendar(attention: int, success: int, total: int) -> str:
    if attention > 0:
        return "attention"
    if success > 0 and success >= max(1, total // 2):
        return "ok"
    if success > 0:
        return "mixed"
    return "unknown"


@router.get("/ops/calendar")
async def get_ops_calendar(
    year: int = Query(..., description="Year, e.g. 2026"),
    month: int = Query(..., ge=1, le=12, description="Month 1-12"),
    _: bool = Depends(require_auth),
):
    """Return per-day state for one calendar month, for the month grid."""
    try:
        cfg = _load_config()
        all_contexts = RunContext.list_all()

        import calendar as _calendar

        today = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
        first_of_month = today.replace(year=year, month=month, day=1)
        days_in_month = _calendar.monthrange(year, month)[1]

        telegram_accounts = list(cfg.telegram.account or []) if cfg.telegram else []
        emby_accounts = list(cfg.emby.account or []) if cfg.emby else []
        subsonic_accounts = list(cfg.subsonic.account or []) if cfg.subsonic else []
        checkiner_enabled = (
            bool(cfg.checkiner.enabled) if cfg.checkiner and cfg.checkiner.enabled is not None else True
        )
        emby_enabled = bool(cfg.emby.enabled) if cfg.emby and cfg.emby.enabled is not None else True
        subsonic_enabled = (
            bool(cfg.subsonic.enabled) if cfg.subsonic and cfg.subsonic.enabled is not None else True
        )

        days: List[Dict[str, Any]] = []
        for day_offset in range(days_in_month):
            day_start = first_of_month + timedelta(days=day_offset)
            day_end = day_start + timedelta(days=1)
            attention = 0
            success = 0
            total = 0

            if checkiner_enabled:
                for account in telegram_accounts:
                    if not (account.enabled and account.checkiner):
                        continue
                    total += 1
                    target = f"{account.phone} 账号签到"
                    day_runs = [
                        ctx
                        for ctx in all_contexts
                        if ctx.description == target
                        and _in_day(ctx, day_start, day_end)
                        and _is_terminal(ctx)
                    ]
                    day_runs.sort(key=_ctx_time, reverse=True)
                    outcome = _infer_checkin_outcome(day_runs[0]) if day_runs else None
                    if outcome in {"failed", "partial_failed"}:
                        attention += 1
                    elif outcome == "success":
                        success += 1

            if emby_enabled:
                for account in emby_accounts:
                    if not account.enabled:
                        continue
                    total += 1
                    records = _history_records("emby.account_history", account.url.host, account.username)
                    status, _, _ = _status_from_history(records, day_start, day_end, False)
                    if status == "failed":
                        attention += 1
                    elif status == "success":
                        success += 1

            if subsonic_enabled:
                for account in subsonic_accounts:
                    if not account.enabled:
                        continue
                    total += 1
                    host = getattr(account.url, "host", None) or str(account.url)
                    records = _history_records("subsonic.account_history", str(host), account.username)
                    status, _, _ = _status_from_history(records, day_start, day_end, False)
                    if status == "failed":
                        attention += 1
                    elif status == "success":
                        success += 1

            days.append(
                {
                    "day": day_start.strftime("%Y-%m-%d"),
                    "day_of_month": day_offset + 1,
                    "state": _day_state_for_calendar(attention, success, total),
                    "attention": attention,
                    "success": success,
                    "total": total,
                    "is_future": day_start > today,
                }
            )

        attention_days = sum(1 for item in days if item["state"] == "attention")
        ok_days = sum(1 for item in days if item["state"] == "ok")

        return {
            "year": year,
            "month": month,
            "days": days,
            "attention_days": attention_days,
            "ok_days": ok_days,
            "summary": (
                f"{attention_days} 天有异常"
                if attention_days > 0
                else (f"全部 {ok_days} 天正常" if ok_days > 0 else "本月暂无足够结果")
            ),
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build ops calendar: {exc}") from exc
