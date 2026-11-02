from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from loguru import logger

from embykeeper.config import config
from embykeeper.cache import cache
from embykeeper.runinfo import RunContext, RunStatus
from embykeeper.schedule import Scheduler
from embykeeper.schema import EmbyAccount
from embykeeper.utils import show_exception, truncate_str
from embykeeper.var import console

from .api import Emby, EmbyConnectError, EmbyError, EmbyPlayError, EmbyRequestError

logger = logger.bind(scheme="embywatcher")


class EmbyManager:
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._schedulers: Dict[str, Scheduler] = {}
        self._scheduler_tasks: Dict[str, asyncio.Task] = {}
        self._keepalive = asyncio.Event()

        config.on_list_change("emby.account", self._handle_account_change)
        config.on_change("emby.enabled", self._handle_config_change)
        config.on_change("emby.time_range", self._handle_schedule_change)
        config.on_change("emby.interval_days", self._handle_schedule_change)
        config.on_change("emby.concurrency", self._handle_runtime_config_change)

    @staticmethod
    def _record_watch_result(account: EmbyAccount, success: bool):
        """Persist per-account keepalive outcome for the daily overview."""
        key = f"emby.account_history.{account.url.host}.{account.username}"
        history = cache.get(key, []) or []
        if not isinstance(history, list):
            history = []
        history.insert(
            0,
            {"status": "success" if success else "failed", "time": datetime.now().isoformat()},
        )
        cache.set(key, history[:30])

    def _module_enabled(self):
        return bool(config.emby.enabled) if config.emby else True

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

        for account in config.emby.account:
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
        task = asyncio.create_task(scheduler.schedule(), name=f"Emby 保活调度 {account_spec}")
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
                logger.warning(f"账号 {spec} 的 Emby 保活调度任务发生错误, 该调度已停止.")
                show_exception(e, regular=False)

        task.add_done_callback(on_done)
        return task

    def _handle_account_change(self, added: List[EmbyAccount], removed: List[EmbyAccount]):
        for account in removed:
            logger.info(f"账号 {self.get_spec(account)} 的 Emby 保活及其计划任务已被清除.")

        for account in added:
            if account.enabled:
                logger.info(f"新增的账号 {self.get_spec(account)} 的 Emby 保活计划任务已添加.")

        self._handle_config_change()

    def _handle_schedule_change(self, *args):
        if not self._module_enabled():
            return

        scheduled = self._refresh_future_schedules()
        if scheduled:
            logger.info("已根据新的配置重新安排未来的 Emby 保活任务, 当前正在执行的任务将继续.")
        else:
            logger.info("没有需要执行的 Emby 保活任务")

    def _handle_runtime_config_change(self, *args):
        if not self._module_enabled():
            return

        logger.info("新的 Emby 并发设置将在下一次保活执行时生效, 当前正在执行的任务不受影响.")

    def _handle_config_change(self, *args):
        self.stop_all()

        if not self._module_enabled():
            logger.info("已根据新的配置停止所有 Emby 保活任务.")
            return

        scheduled = False
        for account_spec, scheduler in self._build_scheduler_map().items():
            self._track_scheduler(account_spec, scheduler)
            scheduled = True

        if scheduled:
            logger.info("已根据新的配置重新安排所有 Emby 保活任务.")
        else:
            logger.info("没有需要执行的 Emby 保活任务")

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

    def schedule_independent_account(self, account: EmbyAccount) -> Optional[Scheduler]:
        if not account.enabled:
            return None

        account_spec = self.get_spec(account)
        time_range = account.time_range or config.emby.time_range
        interval = account.interval_days or config.emby.interval_days

        def on_next_time(t):
            logger.bind(log=True).info(
                f"下一次 Emby 账号 ({account_spec}) 的保活将在 {t.strftime('%m-%d %H:%M %p')} 进行."
            )

        def func(ctx: RunContext):
            existing = self._tasks.pop(account_spec, None)
            if existing:
                existing.cancel()

            task = asyncio.create_task(self._watch_main([account], False))
            self._tasks[account_spec] = task
            return task

        return Scheduler.from_str(
            func=func,
            interval_days=interval,
            time_range=time_range,
            on_next_time=on_next_time,
            sid=f"emby.watch.{account_spec}",
            description=f"Emby 保活任务 - {account_spec}",
        )

    def schedule_unified_accounts(self) -> Optional[Scheduler]:
        unified_accounts = [
            account
            for account in config.emby.account
            if account.enabled and not (account.time_range or account.interval_days)
        ]

        if not unified_accounts:
            return None

        def on_next_time(t):
            logger.bind(log=True).info(f"下一次 Emby 保活将在 {t.strftime('%m-%d %H:%M %p')} 进行.")

        def func(ctx: RunContext):
            existing = self._tasks.pop("unified", None)
            if existing:
                existing.cancel()

            task = asyncio.create_task(self._watch_main(unified_accounts, False))
            self._tasks["unified"] = task
            return task

        return Scheduler.from_str(
            func=func,
            interval_days=config.emby.interval_days,
            time_range=config.emby.time_range,
            on_next_time=on_next_time,
            sid="emby.watch.global",
            description="Emby 保活任务",
        )

    async def schedule_all(self, instant: bool = False):
        self._handle_config_change()

        try:
            await self._keepalive.wait()
        except asyncio.CancelledError:
            self.stop_all()
            raise

    async def play_url(self, url: str):
        parsed = urlparse(url)

        fragment_parts = parsed.fragment.split("?", 1)
        if len(fragment_parts) > 1:
            params = parse_qs(fragment_parts[1])
        else:
            params = {}

        if not params.get("id"):
            logger.error(
                "无效的 URL 格式, 无法解析视频 ID. 应为类似:\nhttps://example.com/web/#/details?id=xxx&serverId=xxx"
            )
            return False

        item_id = params["id"][0]

        account = None
        for candidate in config.emby.account:
            if candidate.url.host == parsed.netloc:
                account = candidate
                break

        if not account:
            logger.error(f"在配置中未找到匹配的 Emby 服务器: {parsed.netloc}")
            return False

        ctx = RunContext.prepare(description="播放指定 URL 视频")
        ctx.start(RunStatus.INITIALIZING)

        emby = Emby(account)
        emby.log = ctx.bind_logger(emby.log)
        try:
            if not await emby.login():
                return ctx.finish(RunStatus.FAIL, "登陆失败")
            emby.log.info("使用以下 Headers:")
            console.rule("Headers")
            headers = emby.build_headers()
            for key, value in headers.items():
                console.print(f"{key.title()}: {value}")
            console.rule()
            item = await emby.get_item(item_id)
            if not item:
                raise ValueError(f"无法找到 ID 为 {item_id} 的视频")
            name = truncate_str(item.get("Name", "(未命名视频)"), 10)
            emby.log.info(f'10 秒后, 将开始播放该视频 300 秒: "{name}"')
            await asyncio.sleep(1)
            emby.log.info(f'开始播放视频 300 秒: "{name}"')
            try:
                await emby.play(item, time=300)
            except EmbyPlayError as e:
                emby.log.error(f"播放失败: {e}")
                return ctx.finish(RunStatus.FAIL, "播放失败")
            return ctx.finish(RunStatus.SUCCESS, "播放成功")
        except EmbyConnectError as e:
            if emby.proxy:
                emby.log.error(f"无法连接到服务器, 可能是您的代理服务器设置错误或无法连通: {e}")
            else:
                emby.log.error(f"无法连接到服务器, 可能是您没有使用代理: {e}")
            return ctx.finish(RunStatus.FAIL, "连接失败")
        except EmbyRequestError as e:
            emby.log.error(f"服务器异常: {e}")
            return ctx.finish(RunStatus.FAIL, "服务器异常")
        except Exception as e:
            emby.log.error("播放视频时发生错误, 播放失败.")
            show_exception(e, regular=False)
            return ctx.finish(RunStatus.ERROR, "异常错误")

    def get_spec(self, account: EmbyAccount):
        return f"{account.username}@{account.name or account.url.host}"

    async def _watch_main(
        self,
        accounts: List[EmbyAccount],
        instant: bool = False,
        description: Optional[str] = None,
        connect_only: bool = False,
    ):
        if not accounts:
            return None

        tasks = []
        sem = asyncio.Semaphore(config.emby.concurrency or 100000)

        ctx = RunContext.prepare(description=description or "使用全局设置的 Emby 统一保活")
        ctx.start(RunStatus.INITIALIZING)
        run_logger = ctx.bind_logger(logger)
        run_logger.info("开始执行 Emby 连接测试." if connect_only else "开始执行 Emby 保活.")

        async def watch_wrapper(account: EmbyAccount, sem: asyncio.Semaphore):
            async with sem:
                try:
                    emby = Emby(account)
                    emby.log = ctx.bind_logger(emby.log)
                except Exception as e:
                    run_logger.error(f"初始化失败: {e}")
                    show_exception(e, regular=False)
                    return account, False

                if not instant:
                    wait = random.uniform(180, 360)
                    emby.log.info(f"播放视频前随机等待 {wait:.0f} 秒.")
                    await asyncio.sleep(wait)

                try:
                    if not account.play_id:
                        emby.log.info("正在登陆并获取首页视频项目.")
                        if not emby.user_id and not await emby.login():
                            emby.log.warning(
                                "连接测试失败: 无法登陆." if connect_only else "保活失败: 无法登陆."
                            )
                            return account, False
                        await emby.load_main_page()
                        if not emby.items:
                            emby.log.warning(
                                "连接测试失败: 无法获取首页中的视频项目"
                                if connect_only
                                else "保活失败: 无法获取首页中的视频项目"
                            )
                            return account, False
                        emby.log.info(f"成功登陆, 获取了 {len(emby.items)} 个首页视频项目.")
                        await asyncio.sleep(random.uniform(2, 5))
                    else:
                        emby.log.info(f"正在登陆并播放您指定的视频, ID 为 {account.play_id}.")
                        if not emby.user_id and not await emby.login():
                            emby.log.warning(
                                "连接测试失败: 无法登陆." if connect_only else "保活失败: 无法登陆."
                            )
                            return account, False
                        item = await emby.get_item(account.play_id)
                        if "Id" not in item:
                            emby.log.warning(
                                "连接测试失败: 无法获取视频项目"
                                if connect_only
                                else "保活失败: 无法获取视频项目"
                            )
                            return account, False
                        emby.items[item["Id"]] = item
                        emby.log.info("成功登陆, 获取了视频项目.")
                        await asyncio.sleep(random.uniform(2, 5))

                    if connect_only:
                        return account, True

                    return account, await emby.watch()
                except EmbyError as e:
                    emby.log.warning(f"{'连接测试失败' if connect_only else '保活失败'}: {e}.")
                    return account, False
                except Exception as e:
                    emby.log.warning(f"{'连接测试失败' if connect_only else '保活失败'}: {e}")
                    show_exception(e, regular=False)
                    return account, False

        for account in accounts:
            if account.enabled:
                tasks.append(watch_wrapper(account, sem))

        failed_accounts = []
        successful_accounts = []
        results = await asyncio.gather(*tasks)
        for account, success in results:
            if not connect_only:
                self._record_watch_result(account, success)
            if success:
                successful_accounts.append(self.get_spec(account))
            else:
                failed_accounts.append(self.get_spec(account))
        fails = len(failed_accounts)

        if fails:
            if len(accounts) == 1:
                run_logger.error(
                    f"{'连接测试失败' if connect_only else '保活失败'}: {', '.join(failed_accounts)}"
                )
            else:
                run_logger.error(
                    f"{'连接测试失败' if connect_only else '保活失败'} ({fails}/{len(tasks)}): {', '.join(failed_accounts)}"
                )
            return ctx.finish(RunStatus.FAIL, "连接测试失败" if connect_only else "保活失败")

        if len(accounts) == 1:
            run_logger.bind(log=True).info(
                f"{'连接测试成功' if connect_only else '保活成功'}: {', '.join(successful_accounts)}."
            )
        else:
            run_logger.bind(log=True).info(
                f"{'连接测试成功' if connect_only else '保活成功'} ({len(tasks)}/{len(tasks)}): {', '.join(successful_accounts)}."
            )
        return ctx.finish(RunStatus.SUCCESS, "连接测试成功" if connect_only else "保活成功")

    async def run_all(self, instant: bool = False):
        if not self._module_enabled():
            return None

        return await self._watch_main(config.emby.account, instant)
