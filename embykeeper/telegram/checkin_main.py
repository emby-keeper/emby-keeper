from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
import random
from typing import Callable, Dict, List, Optional, Tuple, Type

from loguru import logger

from embykeeper.schedule import Scheduler
from embykeeper.schema import TelegramAccount
from embykeeper.config import config
from embykeeper.runinfo import RunContext, RunStatus
from embykeeper.utils import show_exception

from .checkiner import BaseBotCheckin
from .dynamic import extract, get_cls, get_names
from .link import Link
from .session import ClientsSession
from .pyrogram import Client

logger = logger.bind(scheme="telechecker")


@dataclass
class _CheckinSiteSpec:
    key: str
    site_name: str
    cls: Type[BaseBotCheckin]


@dataclass
class _SchedulerSpec:
    key: str
    signature: Tuple
    factory: Callable[[], Scheduler]


@dataclass
class _AccountState:
    account: TelegramAccount
    task: Optional[asyncio.Task] = None
    site_tasks: Dict[str, asyncio.Task] = field(default_factory=dict)
    batch_tasks: Dict[str, asyncio.Task] = field(default_factory=dict)
    reconcile_event: asyncio.Event = field(default_factory=asyncio.Event)
    force_batch_refresh: bool = False
    instant: bool = False
    sem: Optional[asyncio.Semaphore] = None
    batch_results: Dict[str, Tuple[BaseBotCheckin, RunContext]] = field(default_factory=dict)


class CheckinerManager:
    """Check-in manager."""

    def __init__(self):
        self._accounts: Dict[str, _AccountState] = {}
        self._schedulers: Dict[str, Scheduler] = {}
        self._scheduler_tasks: Dict[str, asyncio.Task] = {}
        self._scheduler_signatures: Dict[str, Tuple] = {}
        self._keepalive = asyncio.Event()
        self._reconcile_lock = asyncio.Lock()
        self._reconcile_task: Optional[asyncio.Task] = None
        self._reconcile_dirty = False

        config.on_list_change("telegram.account", self._handle_account_change)
        config.on_change("checkiner", self._handle_config_change)
        config.on_change("site.checkiner", self._handle_config_change)

    def _module_enabled(self):
        return bool(config.checkiner.enabled) if config.checkiner else True

    @staticmethod
    def _account_signature(account: TelegramAccount):
        return (account.phone, account.api_id, account.api_hash, account.session)

    def _request_reconcile(self):
        self._reconcile_dirty = True

        if self._reconcile_task and not self._reconcile_task.done():
            return self._reconcile_task

        self._reconcile_task = asyncio.create_task(self._run_reconcile_loop())
        return self._reconcile_task

    def _cancel_reconcile_task(self):
        if self._reconcile_task and not self._reconcile_task.done():
            self._reconcile_task.cancel()
        self._reconcile_task = None
        self._reconcile_dirty = False

    async def _run_reconcile_loop(self):
        try:
            async with self._reconcile_lock:
                while self._reconcile_dirty:
                    self._reconcile_dirty = False
                    await self._reconcile()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("根据新的配置更新签到任务时出错.")
            show_exception(e, regular=False)
        finally:
            if self._reconcile_task is asyncio.current_task():
                self._reconcile_task = None
            if self._reconcile_dirty:
                self._request_reconcile()

    def _desired_accounts(self):
        if not self._module_enabled():
            return {}

        accounts = config.telegram.account if config.telegram and config.telegram.account else []
        return {a.phone: a for a in accounts if a.enabled and a.checkiner}

    def _ensure_state(self, account: TelegramAccount):
        state = self._accounts.get(account.phone)
        if not state:
            state = _AccountState(account=account)
            self._accounts[account.phone] = state
        else:
            state.account = account
        return state

    def _resolve_site_names(self, account: TelegramAccount):
        if account.site and account.site.checkiner is not None:
            return account.site.checkiner
        if config.site and config.site.checkiner is not None:
            return config.site.checkiner
        return get_names("checkiner")

    @staticmethod
    def _get_site_name(cls: Type[BaseBotCheckin]):
        if hasattr(cls, "templ_name"):
            return cls.templ_name
        return cls.__module__.rsplit(".", 1)[-1]

    @staticmethod
    def _site_name_from_key(key: str):
        return key.split(":", 1)[0]

    def _build_checkin_specs(self, account: TelegramAccount):
        site_names = self._resolve_site_names(account)
        clses: List[Type[BaseBotCheckin]] = extract(get_cls("checkiner", names=site_names))
        specs = []
        for cls in clses:
            site_name = self._get_site_name(cls)
            key = f"{site_name}:{cls.__module__}.{cls.__qualname__}"
            specs.append(_CheckinSiteSpec(key=key, site_name=site_name, cls=cls))
        return specs, site_names, account.checkiner_config or config.checkiner

    def _desired_site_names(self, account: TelegramAccount):
        specs, _, _ = self._build_checkin_specs(account)
        return {spec.site_name for spec in specs}

    def _has_independent_time_range(self, site_name: str, config_to_use) -> bool:
        site_config = config_to_use.get_site_config(site_name)
        return isinstance(site_config, dict) and "time_range" in site_config

    def _build_batch_specs(self, account: TelegramAccount):
        specs, site_names, config_to_use = self._build_checkin_specs(account)
        batch_specs = [
            spec for spec in specs if not self._has_independent_time_range(spec.site_name, config_to_use)
        ]
        return batch_specs, specs, site_names, config_to_use

    def _build_scheduler_specs(self, account: TelegramAccount):
        phone = account.phone
        batch_specs, specs, _, config_to_use = self._build_batch_specs(account)
        desired = {}

        if batch_specs:
            desired[phone] = _SchedulerSpec(
                key=phone,
                signature=("account", str(config_to_use.interval_days), str(config_to_use.time_range)),
                factory=lambda phone=phone, cfg=config_to_use: self._build_account_scheduler(
                    phone,
                    cfg.interval_days,
                    cfg.time_range,
                ),
            )

        for spec in specs:
            if not self._has_independent_time_range(spec.site_name, config_to_use):
                continue

            site_config = config_to_use.get_site_config(spec.site_name)
            site_interval_days = site_config.get("interval_days", config_to_use.interval_days)
            site_time_range = site_config.get("time_range")
            key = f"{phone}.{spec.site_name}"
            desired[key] = _SchedulerSpec(
                key=key,
                signature=("site", spec.site_name, str(site_interval_days), str(site_time_range)),
                factory=lambda phone=phone, site_name=spec.site_name, interval_days=site_interval_days, time_range=site_time_range: self._build_independent_site_scheduler(
                    phone,
                    site_name,
                    interval_days,
                    time_range,
                ),
            )

        return desired

    def _build_account_scheduler(self, phone: str, interval_days, time_range):
        def on_next_time(t: datetime):
            phone_masked = TelegramAccount.get_phone_masked(phone)
            logger.info(f"下一次 \"{phone_masked}\" 账号的签到将在 {t.strftime('%m-%d %H:%M %p')} 进行.")
            date_ctx = RunContext.get_or_create(f"checkiner.date.{t.strftime('%Y%m%d')}")
            account_ctx = RunContext.get_or_create(f"checkiner.account.{phone}")
            return RunContext.prepare(
                description=f"{phone} 账号签到",
                parent_ids=[account_ctx.id, date_ctx.id],
            )

        def func(ctx: RunContext):
            state = self._accounts.get(phone)
            if not state:
                return None
            return self._start_account_task(state, ctx, instant=False)

        return Scheduler.from_str(
            func=func,
            interval_days=interval_days,
            time_range=time_range,
            on_next_time=on_next_time,
            description=f"{phone} 每日签到定时任务",
            sid=f"checkiner.{phone}",
        )

    def _build_independent_site_scheduler(self, phone: str, site_name: str, interval_days, time_range):
        def on_next_time(t: datetime):
            phone_masked = TelegramAccount.get_phone_masked(phone)
            logger.info(
                f"下一次 \"{phone_masked}\" 账号 {site_name} 站点的签到将在 {t.strftime('%m-%d %H:%M %p')} 进行."
            )
            date_ctx = RunContext.get_or_create(f"checkiner.date.{t.strftime('%Y%m%d')}")
            account_ctx = RunContext.get_or_create(f"checkiner.account.{phone}")
            site_ctx = RunContext.get_or_create(f"checkiner.site.{site_name}")
            return RunContext.prepare(
                description=f"{phone} 账号 {site_name} 站点签到",
                parent_ids=[account_ctx.id, date_ctx.id, site_ctx.id],
            )

        def func(ctx: RunContext):
            return self._start_standalone_site_task(ctx, phone, site_name)

        return Scheduler.from_str(
            func=func,
            interval_days=interval_days,
            time_range=time_range,
            on_next_time=on_next_time,
            description=f"{phone} 账号 {site_name} 站点签到定时任务",
            sid=f"checkiner.{phone}.{site_name}",
        )

    def _start_scheduler(self, spec: _SchedulerSpec):
        scheduler = spec.factory()
        self._schedulers[spec.key] = scheduler
        self._scheduler_signatures[spec.key] = spec.signature
        task = asyncio.create_task(scheduler.schedule(), name=f"Telegram 签到调度 {spec.key}")
        self._scheduler_tasks[spec.key] = task
        task.add_done_callback(
            lambda t, key=spec.key, sched=scheduler: self._on_scheduler_done(key, sched, t)
        )
        return task

    def _on_scheduler_done(self, key: str, scheduler: Scheduler, task: asyncio.Task):
        if self._scheduler_tasks.get(key) is task:
            del self._scheduler_tasks[key]
        if self._schedulers.get(key) is scheduler:
            del self._schedulers[key]
        self._scheduler_signatures.pop(key, None)

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"账号 {key} 的 Telegram 签到调度任务发生错误, 该调度已停止.")
            show_exception(e, regular=False)

    async def _cancel_scheduler_keys(self, keys):
        tasks = []
        for key in set(keys):
            task = self._scheduler_tasks.pop(key, None)
            if task and not task.done():
                task.cancel()
                tasks.append(task)
            self._schedulers.pop(key, None)
            self._scheduler_signatures.pop(key, None)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _cancel_batch_tasks(self, state: _AccountState, keys=None):
        selected = list(keys if keys is not None else state.batch_tasks.keys())
        tasks = []

        for key in selected:
            task = state.batch_tasks.pop(key, None)
            if not task:
                continue
            if not task.done():
                task.cancel()
                tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _cancel_site_tasks(self, state: _AccountState, sites=None):
        selected = list(sites if sites is not None else state.site_tasks.keys())
        tasks = []

        for site_name in selected:
            task = state.site_tasks.pop(site_name, None)
            if not task:
                continue
            if not task.done():
                task.cancel()
                tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _cancel_removed_site_tasks(self, state: _AccountState, desired_sites):
        removed_sites = [site_name for site_name in state.site_tasks.keys() if site_name not in desired_sites]
        if removed_sites:
            await self._cancel_site_tasks(state, removed_sites)

        removed_batch_keys = [
            key for key in state.batch_tasks.keys() if self._site_name_from_key(key) not in desired_sites
        ]
        if removed_batch_keys:
            await self._cancel_batch_tasks(state, removed_batch_keys)

    async def _reconcile_schedulers(self, desired_specs):
        current_keys = set(self._scheduler_tasks) | set(self._schedulers) | set(self._scheduler_signatures)
        desired_keys = set(desired_specs)
        restart_keys = {
            key
            for key in current_keys & desired_keys
            if self._scheduler_signatures.get(key) != desired_specs[key].signature
        }

        await self._cancel_scheduler_keys((current_keys - desired_keys) | restart_keys)

        for key, spec in desired_specs.items():
            if key in self._scheduler_tasks and not self._scheduler_tasks[key].done():
                continue
            self._start_scheduler(spec)

    async def _stop_accounts(self, phones):
        tasks = []
        scheduler_keys = []

        for phone in set(phones):
            state = self._accounts.pop(phone, None)
            if state:
                if state.task and not state.task.done():
                    state.task.cancel()
                    tasks.append(state.task)

                for task in list(state.batch_tasks.values()) + list(state.site_tasks.values()):
                    if task and not task.done():
                        task.cancel()
                        tasks.append(task)

                state.batch_tasks.clear()
                state.site_tasks.clear()
                state.batch_results.clear()
                state.sem = None

            scheduler_keys.extend(
                key
                for key in set(list(self._schedulers.keys()) + list(self._scheduler_tasks.keys()))
                if key == phone or key.startswith(f"{phone}.")
            )

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        if scheduler_keys:
            await self._cancel_scheduler_keys(scheduler_keys)

    async def _reconcile(self):
        desired_accounts = self._desired_accounts()
        current_phones = set(self._accounts)
        desired_phones = set(desired_accounts)

        restart_phones = {
            phone
            for phone in current_phones & desired_phones
            if self._account_signature(self._accounts[phone].account)
            != self._account_signature(desired_accounts[phone])
        }

        await self._stop_accounts((current_phones - desired_phones) | restart_phones)

        if not self._module_enabled():
            logger.info("已根据新的配置停止所有签到任务.")
            return

        for account in desired_accounts.values():
            self._ensure_state(account)

        desired_scheduler_specs = {}
        for account in desired_accounts.values():
            desired_scheduler_specs.update(self._build_scheduler_specs(account))

        await self._reconcile_schedulers(desired_scheduler_specs)

        for phone, account in desired_accounts.items():
            state = self._accounts.get(phone)
            if not state:
                continue

            state.account = account
            await self._cancel_removed_site_tasks(state, self._desired_site_names(account))

            if state.task and not state.task.done():
                state.reconcile_event.set()

        if not desired_scheduler_specs and not any(
            state.task or state.site_tasks or state.batch_tasks for state in self._accounts.values()
        ):
            logger.info("没有需要执行的 Telegram 机器人签到任务")
        else:
            logger.info("已根据新的配置收敛签到任务.")

    def _on_account_task_done(self, phone: str, task: asyncio.Task):
        state = self._accounts.get(phone)
        if state and state.task is task:
            state.task = None
            state.sem = None
            state.instant = False
            state.reconcile_event.clear()

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"账户 {phone} 的签到任务发生错误, 签到已停止.")
            show_exception(e, regular=False)

    def _on_batch_task_done(self, phone: str, key: str, site_name: str, ctx: RunContext, task: asyncio.Task):
        state = self._accounts.get(phone)
        if state and state.batch_tasks.get(key) is task:
            del state.batch_tasks[key]

        try:
            checkiner, result = task.result()
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.warning(f"账户 {phone} 的 {site_name} 站点签到任务发生错误.")
            show_exception(e, regular=False)
            return

        if state:
            state.batch_results[key] = (checkiner, result)

        if result.status == RunStatus.RESCHEDULE and checkiner.ctx.next_time:
            self.schedule_site(ctx, checkiner.ctx.next_time, phone, site_name, reschedule=True)

    def _on_site_task_done(self, phone: str, site_name: str, task: asyncio.Task):
        state = self._accounts.get(phone)
        if state and state.site_tasks.get(site_name) is task:
            del state.site_tasks[site_name]

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"账户 {phone} 的 {site_name} 站点补签到任务发生错误.")
            show_exception(e, regular=False)

    def _handle_config_change(self, *args):
        self._request_reconcile()

    def _handle_account_change(self, added: List[TelegramAccount], removed: List[TelegramAccount]):
        self._request_reconcile()

    def stop_account(self, phone: str):
        state = self._accounts.pop(phone, None)
        if state:
            if state.task:
                state.task.cancel()
            for task in list(state.batch_tasks.values()) + list(state.site_tasks.values()):
                task.cancel()

        scheduler_keys = [
            key
            for key in set(list(self._schedulers.keys()) + list(self._scheduler_tasks.keys()))
            if key == phone or key.startswith(f"{phone}.")
        ]
        for key in scheduler_keys:
            scheduler_task = self._scheduler_tasks.pop(key, None)
            if scheduler_task:
                scheduler_task.cancel()
            self._schedulers.pop(key, None)
            self._scheduler_signatures.pop(key, None)

    def stop_all(self):
        self._cancel_reconcile_task()

        for phone in list(self._accounts.keys()):
            self.stop_account(phone)

        for key, scheduler_task in list(self._scheduler_tasks.items()):
            scheduler_task.cancel()
            self._scheduler_tasks.pop(key, None)
        self._schedulers.clear()
        self._scheduler_signatures.clear()

    def _start_account_task(self, state: _AccountState, ctx: RunContext, instant: bool = False):
        if state.task and not state.task.done():
            state.instant = state.instant or instant
            state.force_batch_refresh = True
            state.reconcile_event.set()
            return state.task

        state.instant = instant
        state.force_batch_refresh = True
        state.batch_results.clear()
        task = asyncio.create_task(
            self._run_account_task(state, ctx),
            name=f"Telegram 签到任务 {state.account.phone}",
        )
        state.task = task
        task.add_done_callback(lambda t, phone=state.account.phone: self._on_account_task_done(phone, t))
        return task

    async def _run_batch_site(self, checkiner: BaseBotCheckin, sem: asyncio.Semaphore, wait=0):
        if config.debug_cron:
            wait = 0.1
        if wait > 0:
            checkiner.log.debug(f"随机启动等待: 将等待 {wait:.2f} 分钟以启动.")
        await asyncio.sleep(wait * 60)
        async with sem:
            result = await checkiner._start()
            return checkiner, result

    def _start_batch_site_task(
        self, state: _AccountState, ctx: RunContext, client: Client, spec: _CheckinSiteSpec
    ):
        config_to_use = state.account.checkiner_config or config.checkiner
        site_ctx = RunContext.prepare(f"{spec.site_name} 站点签到", parent_ids=ctx.id)
        checkiner = spec.cls(
            client,
            context=site_ctx,
            retries=config_to_use.retries,
            timeout=config_to_use.timeout,
            config=config_to_use.get_site_config(spec.site_name),
        )
        wait = 0 if state.instant else random.uniform(0, config_to_use.random_start)
        task = asyncio.create_task(
            self._run_batch_site(checkiner, state.sem, wait),
            name=f"Telegram 签到子任务 {state.account.phone}.{spec.site_name}",
        )
        task.add_done_callback(
            lambda t, phone=state.account.phone, key=spec.key, site_name=spec.site_name, root_ctx=ctx: self._on_batch_task_done(
                phone,
                key,
                site_name,
                root_ctx,
                t,
            )
        )
        state.batch_tasks[spec.key] = task
        return checkiner.name

    def _start_standalone_site_task(self, ctx: RunContext, phone: str, site_name: str):
        state = self._accounts.get(phone)
        if not state:
            return None

        if site_name not in self._desired_site_names(state.account):
            return None

        existing = state.site_tasks.get(site_name)
        if existing and not existing.done():
            existing.cancel()

        task = asyncio.create_task(
            self._run_single_site(ctx, phone, site_name),
            name=f"Telegram 单站点签到任务 {phone}.{site_name}",
        )
        task.add_done_callback(
            lambda t, phone=phone, site_name=site_name: self._on_site_task_done(phone, site_name, t)
        )
        state.site_tasks[site_name] = task
        return task

    async def _run_account_task(self, state: _AccountState, ctx: RunContext):
        try:
            async with ClientsSession([state.account]) as clients:
                async for _, client in clients:
                    await self._run_account(ctx, state, client)
        finally:
            await self._cancel_batch_tasks(state)
            state.sem = None

    async def _run_account(self, ctx: RunContext, state: _AccountState, client: Client):
        log = logger.bind(username=client.me.full_name)
        batch_specs, specs, site_names, config_to_use = self._build_batch_specs(state.account)

        if not specs:
            if site_names is not None:
                log.warning("没有任何有效签到站点, 签到将跳过.")
            return

        if not batch_specs:
            return

        if not await Link(client).auth("checkiner", log_func=log.error):
            return

        state.sem = asyncio.Semaphore(config_to_use.concurrency)
        state.batch_results.clear()
        state.reconcile_event.set()

        while True:
            if state.reconcile_event.is_set():
                state.reconcile_event.clear()
                await self._reconcile_running_account(state, ctx, client, log)

            if not state.batch_tasks:
                break

            waiter = asyncio.create_task(state.reconcile_event.wait())
            try:
                await asyncio.wait([waiter, *state.batch_tasks.values()], return_when=asyncio.FIRST_COMPLETED)
            finally:
                if not waiter.done():
                    waiter.cancel()
                await asyncio.gather(waiter, return_exceptions=True)

        finish_status, finish_info = self._log_batch_summary(state.batch_results, log)
        state.batch_results.clear()
        if finish_status is not None and not ctx.end_time:
            ctx.finish(finish_status, finish_info)

    async def _reconcile_running_account(self, state: _AccountState, ctx: RunContext, client: Client, log):
        batch_specs, specs, site_names, _ = self._build_batch_specs(state.account)

        if not specs:
            await self._cancel_batch_tasks(state)
            if site_names is not None:
                log.warning("没有任何有效签到站点, 签到将跳过.")
            return

        if state.force_batch_refresh:
            await self._cancel_batch_tasks(state)
            state.force_batch_refresh = False

        desired_keys = {spec.key for spec in batch_specs}
        removed_keys = [key for key in state.batch_tasks.keys() if key not in desired_keys]
        if removed_keys:
            await self._cancel_batch_tasks(state, removed_keys)

        started_names = []
        for spec in batch_specs:
            if spec.key in state.batch_tasks:
                continue
            if spec.site_name in state.site_tasks:
                await self._cancel_site_tasks(state, [spec.site_name])
            started_names.append(self._start_batch_site_task(state, ctx, client, spec))

        if started_names:
            log.info(f'已启用签到器: {", ".join(started_names)}')

    @staticmethod
    def _log_batch_summary(results, log):
        if not results:
            return None, None

        failed = []
        ignored = []
        successful = []
        checked = []

        for checkiner, result in results.values():
            if result.status == RunStatus.IGNORE:
                ignored.append(checkiner.name)
            elif result.status == RunStatus.SUCCESS:
                successful.append(checkiner.name)
            elif result.status in (RunStatus.NONEED, RunStatus.RESCHEDULE):
                checked.append(checkiner.name)
            else:
                failed.append(checkiner.name)

        spec = f"共{len(successful) + len(checked) + len(failed) + len(ignored)}个"
        if successful:
            spec += f", {len(successful)}成功"
        if checked:
            spec += f", {len(checked)}已签到而跳过"
        if failed:
            spec += f", {len(failed)}失败"
        if ignored:
            spec += f", {len(ignored)}跳过"

        if failed:
            msg = "签到部分失败" if successful or checked else "签到失败"
            log.bind(log=True).error(f"{msg} ({spec}): {', '.join(failed)}")
            # Keep FAIL for both total and partial failure; distinguish via status_info.
            return RunStatus.FAIL, msg
        else:
            log.bind(log=True).info(f"签到成功 ({spec}).")
            return RunStatus.SUCCESS, "签到成功"

    def schedule_site(
        self, ctx: RunContext, at: datetime, phone: str, site_name: str, reschedule: bool = False
    ):
        state = self._accounts.get(phone)
        if not state:
            return None

        try:
            account_ctx = RunContext.get_or_create(f"checkiner.account.{phone}")

            if reschedule:
                description = f"{phone} 账号 {site_name} 站点重新签到"
            else:
                description = f"{phone} 账号 {site_name} 站点签到"

            site_ctx = RunContext.prepare(description=description, parent_ids=[account_ctx.id, ctx.id])
            site_ctx.reschedule = (ctx.reschedule or 0) + 1

            async def _schedule():
                delay = (at - datetime.now()).total_seconds()
                if delay > 0:
                    if reschedule:
                        logger.debug(
                            f"已安排账户 {phone} 的 {site_name} 站点在 {at.strftime('%m-%d %H:%M %p')} 重新尝试签到."
                        )
                    else:
                        logger.debug(
                            f"已安排账户 {phone} 的 {site_name} 站点在 {at.strftime('%m-%d %H:%M %p')} 签到."
                        )
                    await asyncio.sleep(delay)
                await self._run_single_site(site_ctx, phone, site_name)

            existing = state.site_tasks.get(site_name)
            if existing and not existing.done():
                existing.cancel()

            task = asyncio.create_task(
                _schedule(),
                name=f"Telegram 补签到任务 {phone}.{site_name}",
            )
            task.add_done_callback(
                lambda t, phone=phone, site_name=site_name: self._on_site_task_done(phone, site_name, t)
            )
            state.site_tasks[site_name] = task
            return task
        except Exception as e:
            if reschedule:
                logger.warning(f"重新安排 {site_name} 站点签到时间失败: {e}")
            else:
                logger.warning(f"安排 {site_name} 站点签到时间失败: {e}")
            show_exception(e, regular=False)
            return None

    async def _run_single_site(self, ctx: RunContext, phone: str, site_name: str):
        state = self._accounts.get(phone)
        if not state:
            return

        if site_name not in self._desired_site_names(state.account):
            return

        account = state.account

        async with ClientsSession([account]) as clients:
            async for _, client in clients:
                clses = get_cls("checkiner", names=[site_name])
                if not clses:
                    return

                cls = clses[0]
                config_to_use = account.checkiner_config or config.checkiner

                checkiner: BaseBotCheckin = cls(
                    client,
                    context=ctx,
                    retries=config_to_use.retries,
                    timeout=config_to_use.timeout,
                    config=config_to_use.get_site_config(site_name),
                )

                log = logger.bind(username=client.me.full_name, name=checkiner.name)

                result = await checkiner._start()
                if result.status == RunStatus.SUCCESS:
                    log.info("重新签到成功.")
                elif result.status == RunStatus.NONEED:
                    log.info("多次重新签到后依然为已签到状态, 已跳过.")
                elif result.status == RunStatus.RESCHEDULE:
                    if checkiner.ctx.next_time:
                        log.debug("继续等待重新签到.")
                        self.schedule_site(ctx, checkiner.ctx.next_time, phone, site_name, reschedule=True)
                else:
                    log.debug("站点重新签到失败.")

    def new_ctx(self):
        now = datetime.now()
        return RunContext.get_or_create(
            f"checkiner.run.{now.timestamp()}",
            description=f"{now.strftime('%Y-%m-%d')} 签到",
        )

    async def run_account(self, ctx: RunContext, account: TelegramAccount, instant: bool = False):
        state = self._ensure_state(account)
        task = self._start_account_task(state, ctx, instant=instant)
        if task:
            return await task

    async def run_all(self, instant: bool = False):
        if not self._module_enabled():
            return None

        accounts = [a for a in config.telegram.account if a.enabled and a.checkiner]
        tasks = [
            self._start_account_task(
                self._ensure_state(account), RunContext.prepare("运行全部签到器"), instant
            )
            for account in accounts
        ]
        tasks = [task for task in tasks if task]

        try:
            if tasks:
                await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def schedule_all(self):
        task = self._request_reconcile()
        if task:
            await task

        try:
            await self._keepalive.wait()
        except asyncio.CancelledError:
            self.stop_all()
            raise
