from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Dict, List, Optional
from loguru import logger

from embykeeper.config import config
from embykeeper.cache import cache
from embykeeper.runinfo import RunContext, RunStatus
from embykeeper.schedule import Scheduler
from embykeeper.schema import SubsonicAccount
from embykeeper.utils import show_exception

from .player import SubsonicPlayer

logger = logger.bind(scheme="subsonic")


class SubsonicManager:
    def get_spec(self, a: SubsonicAccount):
        return f"{a.username}@{a.name or a.url.host}"

    @staticmethod
    def _record_listen_result(account: SubsonicAccount, success: bool):
        """Persist per-account keepalive outcome for the daily overview."""
        key = f"subsonic.account_history.{account.url.host}.{account.username}"
        history = cache.get(key, []) or []
        if not isinstance(history, list):
            history = []
        history.insert(
            0,
            {"status": "success" if success else "failed", "time": datetime.now().isoformat()},
        )
        cache.set(key, history[:30])

    async def _listen_main(
        self,
        accounts: List[SubsonicAccount],
        instant: bool = False,
        description: Optional[str] = None,
        connect_only: bool = False,
    ):
        if not accounts:
            return None
        logger.info("开始执行 Subsonic 连接测试." if connect_only else "开始执行 Subsonic 保活.")
        tasks = []
        sem = asyncio.Semaphore(config.subsonic.concurrency or 100000)

        ctx = RunContext.prepare(description=description or "使用全局设置的 Subsonic 统一保活")
        ctx.start(RunStatus.INITIALIZING)

        async def watch_wrapper(account: SubsonicAccount, sem):
            async with sem:
                try:
                    player = SubsonicPlayer(account)
                    player.log = ctx.bind_logger(player.log)
                except Exception as e:
                    logger.error(f"初始化失败: {e}")
                    show_exception(e, regular=False)
                    return account, False
                if not instant:
                    wait = random.uniform(180, 360)
                    player.log.info(f"播放音频前随机等待 {wait:.0f} 秒.")
                    await asyncio.sleep(wait)
                try:
                    subsonic = await player.login()
                    if not subsonic:
                        return account, False
                    if connect_only:
                        return account, True
                    await asyncio.sleep(random.uniform(2, 5))
                    return account, await player.play(subsonic)
                except Exception as e:
                    player.log.error(f"播放任务执行失败: {e}")
                    show_exception(e, regular=False)
                    return account, False

        for account in accounts:
            if account.enabled:
                tasks.append(watch_wrapper(account, sem))

        failed_accounts = []
        successful_accounts = []
        results = await asyncio.gather(*tasks)
        for a, success in results:
            if not connect_only:
                self._record_listen_result(a, success)
            if success:
                successful_accounts.append(self.get_spec(a))
            else:
                failed_accounts.append(self.get_spec(a))
        fails = len(failed_accounts)

        if fails:
            if len(accounts) == 1:
                logger.error(
                    f"{'连接测试失败' if connect_only else '保活失败'}: {', '.join(failed_accounts)}"
                )
            else:
                logger.error(
                    f"{'连接测试失败' if connect_only else '保活失败'} ({fails}/{len(tasks)}): {', '.join(failed_accounts)}"
                )
            return ctx.finish(RunStatus.FAIL, f"连接测试失败" if connect_only else "保活失败")
        if len(accounts) == 1:
            logger.bind(log=True).info(
                f"{'连接测试成功' if connect_only else '保活成功'}: {', '.join(successful_accounts)}."
            )
        else:
            logger.bind(log=True).info(
                f"{'连接测试成功' if connect_only else '保活成功'} ({len(tasks)}/{len(tasks)}): {', '.join(successful_accounts)}."
            )
        return ctx.finish(RunStatus.SUCCESS, f"连接测试成功" if connect_only else "保活成功")

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._schedulers: Dict[str, Scheduler] = {}
        self._scheduler_tasks: Dict[str, asyncio.Task] = {}
        self._keepalive = asyncio.Event()

        config.on_list_change("subsonic.account", self._handle_account_change)
        config.on_change("subsonic.enabled", self._handle_config_change)
        config.on_change("subsonic.time_range", self._handle_schedule_change)
        config.on_change("subsonic.interval_days", self._handle_schedule_change)
        config.on_change("subsonic.concurrency", self._handle_runtime_config_change)

    def _module_enabled(self):
        return bool(config.subsonic.enabled) if config.subsonic else True

    def _has_running_task(self, account_spec: str):
        task = self._tasks.get(account_spec)
        return bool(task and not task.done())

    def _stop_scheduler(self, account_spec: str):
        scheduler_task = self._scheduler_tasks.pop(account_spec, None)
        if scheduler_task:
            scheduler_task.cancel()

        self._schedulers.pop(account_spec, None)

    def _build_scheduler_map(self):
        schedulers: Dict[str, Scheduler] = {}

        unified_scheduler = self.schedule_unified_accounts()
        if unified_scheduler:
            schedulers["unified"] = unified_scheduler

        for account in config.subsonic.account:
            if account.enabled and (account.time_range or account.interval_days):
                scheduler = self.schedule_independent_account(account)
                if scheduler:
                    schedulers[self.get_spec(account)] = scheduler

        return schedulers

    def _update_scheduler(self, account_spec: str, scheduler: Scheduler):
        existing = self._schedulers.get(account_spec)
        if not existing:
            return False

        existing.func = scheduler.func
        existing.days = scheduler.days
        existing.start_time = scheduler.start_time
        existing.end_time = scheduler.end_time
        existing.description = scheduler.description
        existing.on_next_time = scheduler.on_next_time
        existing._next_time = None
        return True

    def _refresh_future_schedules(self):
        scheduler_map = self._build_scheduler_map()
        current_specs = set(self._schedulers.keys()) | set(self._scheduler_tasks.keys())
        desired_specs = set(scheduler_map.keys())

        for account_spec in current_specs - desired_specs:
            if self._has_running_task(account_spec) and account_spec in self._schedulers:
                self._schedulers[account_spec].days = [0, 0]
                self._schedulers[account_spec]._next_time = None
            else:
                self._stop_scheduler(account_spec)

        for account_spec, scheduler in scheduler_map.items():
            if self._has_running_task(account_spec) and self._update_scheduler(account_spec, scheduler):
                continue

            self._stop_scheduler(account_spec)
            self._track_scheduler(account_spec, scheduler)

        return bool(scheduler_map)

    def _track_scheduler(self, account_spec: str, scheduler: Scheduler):
        existing = self._scheduler_tasks.get(account_spec)
        if existing and not existing.done():
            existing.cancel()

        self._schedulers[account_spec] = scheduler
        task = asyncio.create_task(scheduler.schedule(), name=f"Subsonic 保活调度 {account_spec}")
        self._scheduler_tasks[account_spec] = task

        def on_done(t: asyncio.Task, spec: str = account_spec):
            if self._scheduler_tasks.get(spec) is t:
                del self._scheduler_tasks[spec]
            if self._schedulers.get(spec) is scheduler:
                del self._schedulers[spec]
            try:
                t.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"账号 {spec} 的 Subsonic 保活调度任务发生错误, 该调度已停止.")
                show_exception(e, regular=False)

        task.add_done_callback(on_done)
        return task

    def _handle_account_change(self, added: List[SubsonicAccount], removed: List[SubsonicAccount]):
        for account in removed:
            logger.info(f"账号 {self.get_spec(account)} 的 Subsonic 保活及其计划任务已被清除.")

        for account in added:
            if account.enabled:
                logger.info(f"新增的账号 {self.get_spec(account)} 的 Subsonic 保活计划任务已添加.")

        self._handle_config_change()

    def _handle_schedule_change(self, *args):
        if not self._module_enabled():
            return

        scheduled = self._refresh_future_schedules()
        if scheduled:
            logger.info("已根据新的配置重新安排未来的 Subsonic 保活任务, 当前正在执行的任务将继续.")
        else:
            logger.info("没有需要执行的 Subsonic 保活任务")

    def _handle_runtime_config_change(self, *args):
        if not self._module_enabled():
            return

        logger.info("新的 Subsonic 并发设置将在下一次保活执行时生效, 当前正在执行的任务不受影响.")

    def _handle_config_change(self, *args):
        self.stop_all()

        if not self._module_enabled():
            logger.info("已根据新的配置停止所有 Subsonic 保活任务.")
            return

        scheduled = False
        for account_spec, scheduler in self._build_scheduler_map().items():
            self._track_scheduler(account_spec, scheduler)
            scheduled = True

        if scheduled:
            logger.info("已根据新的配置重新安排所有 Subsonic 保活任务.")
        else:
            logger.info("没有需要执行的 Subsonic 保活任务")

    def stop_account(self, account_spec: str):
        self._stop_scheduler(account_spec)

        task = self._tasks.pop(account_spec, None)
        if task:
            task.cancel()

    def stop_unified_accounts(self):
        self.stop_account("unified")

    def stop_all(self):
        for account_spec in list(self._scheduler_tasks.keys()):
            self.stop_account(account_spec)

        for account_spec in list(self._tasks.keys()):
            self.stop_account(account_spec)

    def schedule_independent_account(self, account: SubsonicAccount) -> Optional[Scheduler]:
        if not account.enabled:
            return None

        account_spec = self.get_spec(account)
        time_range = account.time_range or config.subsonic.time_range
        interval = account.interval_days or config.subsonic.interval_days

        def on_next_time(t):
            logger.bind(log=True).info(
                f"下一次 Subsonic 账号 ({account_spec}) 的保活将在 {t.strftime('%m-%d %H:%M %p')} 进行."
            )

        def func(ctx: RunContext):
            existing = self._tasks.pop(account_spec, None)
            if existing:
                existing.cancel()

            task = asyncio.create_task(self._listen_main([account], False))
            self._tasks[account_spec] = task
            return task

        return Scheduler.from_str(
            func=func,
            interval_days=interval,
            time_range=time_range,
            on_next_time=on_next_time,
            sid=f"subsonic.watch.{account_spec}",
            description=f"Subsonic 保活任务 - {account_spec}",
        )

    def schedule_unified_accounts(self) -> Optional[Scheduler]:
        unified_accounts = [
            a for a in config.subsonic.account if a.enabled and not (a.time_range or a.interval_days)
        ]

        if not unified_accounts:
            return None

        def on_next_time(t):
            logger.bind(log=True).info(f"下一次 Subsonic 保活将在 {t.strftime('%m-%d %H:%M %p')} 进行.")

        def func(ctx: RunContext):
            existing = self._tasks.pop("unified", None)
            if existing:
                existing.cancel()

            task = asyncio.create_task(self._listen_main(unified_accounts, False))
            self._tasks["unified"] = task
            return task

        return Scheduler.from_str(
            func=func,
            interval_days=config.subsonic.interval_days,
            time_range=config.subsonic.time_range,
            on_next_time=on_next_time,
            sid="subsonic.watch.global",
            description="Subsonic 保活任务",
        )

    async def run_all(self, instant: bool = False):
        if not self._module_enabled():
            return None

        return await self._listen_main(config.subsonic.account, instant)

    async def schedule_all(self, instant: bool = False):
        self._handle_config_change()

        try:
            await self._keepalive.wait()
        except asyncio.CancelledError:
            self.stop_all()
            raise
