import asyncio
import random
from typing import List, Dict, Set, Optional
from urllib.parse import parse_qs, urlparse
from datetime import datetime

from loguru import logger

from embykeeper.config import config
from embykeeper.schedule import Scheduler
from embykeeper.utils import show_exception, truncate_str
from embykeeper.runinfo import RunContext, RunStatus
from embykeeper.var import console
from embykeeper.schema import EmbyAccount

from embykeeper.utils import AsyncTaskPool

from .api import Emby, EmbyPlayError, EmbyConnectError, EmbyRequestError, EmbyError


logger = logger.bind(scheme="embywatcher")


class EmbyManager:
    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}  # account_spec -> task
        self._schedulers: Dict[str, Scheduler] = {}  # account_spec -> scheduler
        self._running: Set[str] = set()  # Currently running account_specs
        self._pool = AsyncTaskPool()

        config.on_list_change("emby.account", self._handle_account_change)

    def _handle_account_change(self, added: List[EmbyAccount], removed: List[EmbyAccount]):
        """Handle account additions and removals"""
        need_reschedule_unified = False

        for account in removed:
            spec = self.get_spec(account)
            if account.time_range or account.interval_days:
                # 独立账号，直接移除其任务
                self.stop_account(spec)
                logger.info(f"账号 {spec} 的 Emby 保活及其计划任务已被清除.")
            else:
                # 整体账号被移除，标记需要重新调度
                need_reschedule_unified = True
                logger.info(f"账号 {spec} Emby 保活已被移除，将重新调度保活任务.")

        for account in added:
            if account.enabled:
                if account.time_range or account.interval_days:
                    # 新增独立账号，添加其调度任务
                    scheduler = self.schedule_independent_account(account)
                    if scheduler:
                        self._pool.add(scheduler.schedule())
                        logger.info(f"新增的账号 {self.get_spec(account)} 的 Emby 保活计划任务已添加.")
                else:
                    # 新增整体账号，标记需要重新调度
                    need_reschedule_unified = True
                    logger.debug(f"新增的账号 {self.get_spec(account)}，将重新调度 Emby 保活任务.")

        if need_reschedule_unified:
            # 重新调度整体任务
            self.stop_unified_accounts()
            self.schedule_unified_accounts()

    def stop_account(self, account_spec: str):
        """Stop scheduling and running tasks for an independent account"""
        if account_spec in self._schedulers:
            del self._schedulers[account_spec]

        if account_spec in self._tasks:
            self._tasks[account_spec].cancel()
            del self._tasks[account_spec]

        self._running.discard(account_spec)

    def stop_unified_accounts(self):
        """Stop the unified scheduling task"""
        if "unified" in self._schedulers:
            del self._schedulers["unified"]

        if "unified" in self._tasks:
            self._tasks["unified"].cancel()
            del self._tasks["unified"]

    def schedule_independent_account(self, account: EmbyAccount) -> Optional[Scheduler]:
        """Schedule emby watch for an independent account"""
        if not account.enabled:
            return None

        account_spec = self.get_spec(account)
        time_range = account.time_range or config.emby.time_range
        interval = account.interval_days or config.emby.interval_days

        def make_on_next_time(spec):
            return lambda t: logger.bind(log=True).info(
                f"下一次 Emby 账号 ({spec}) 的保活将在 {t.strftime('%m-%d %H:%M %p')} 进行."
            )

        def func(ctx: RunContext):
            task = self._tasks[self.get_spec(account)] = asyncio.create_task(
                self._watch_main([account], False)
            )
            return task

        scheduler = Scheduler.from_str(
            func=func,
            interval_days=interval,
            time_range=time_range,
            on_next_time=make_on_next_time(account_spec),
            sid=f"emby.watch.{account_spec}",
            description=f"Emby 保活任务 - {account_spec}",
        )
        self._schedulers[account_spec] = scheduler
        return scheduler

    def schedule_unified_accounts(self):
        """Schedule unified emby watch for global accounts"""
        unified_accounts = [
            a for a in config.emby.account if a.enabled and not (a.time_range or a.interval_days)
        ]

        if not unified_accounts:
            return None

        on_next_time = lambda t: logger.bind(log=True).info(
            f"下一次 Emby 保活将在 {t.strftime('%m-%d %H:%M %p')} 进行."
        )

        def func(ctx: RunContext):
            task = self._tasks["unified"] = asyncio.create_task(self._watch_main(unified_accounts, False))
            return task

        scheduler = Scheduler.from_str(
            func=func,
            interval_days=config.emby.interval_days,
            time_range=config.emby.time_range,
            on_next_time=on_next_time,
            sid="emby.watch.global",
            description="Emby 保活任务",
        )
        self._schedulers["unified"] = scheduler
        self._pool.add(scheduler.schedule())

    async def schedule_all(self, instant: bool = False):
        """Start scheduling emby watch for all accounts"""
        # Schedule unified accounts
        self.schedule_unified_accounts()

        # Schedule independent accounts
        for account in config.emby.account:
            if account.enabled and (account.time_range or account.interval_days):
                scheduler = self.schedule_independent_account(account)
                if scheduler:
                    self._pool.add(scheduler.schedule())

        if not self._schedulers:
            logger.info("没有需要执行的 Emby 保活任务")
            return None

        await self._pool.wait()

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

        iid = params["id"][0]

        # 在config中查找匹配的emby配置
        account = None
        for a in config.emby.account:
            if a.url.host == parsed.netloc:
                account = a
                break

        if not account:
            logger.error(f"在配置中未找到匹配的 Emby 服务器: {parsed.netloc}")
            return False

        ctx = RunContext.prepare(description="播放指定 URL 视频")
        ctx.start(RunStatus.INITIALIZING)

        emby = Emby(account)
        try:
            if not await emby.login():
                return ctx.finish(RunStatus.FAIL, "登陆失败")
            emby.log.info("使用以下 Headers:")
            console.rule("Headers")
            headers = emby.build_headers()
            for k, v in headers.items():
                console.print(f"{k.title()}: {v}")
            console.rule()
            item = await emby.get_item(iid)
            if not item:
                raise ValueError(f"无法找到 ID 为 {iid} 的视频")
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

    def get_spec(self, a: EmbyAccount):
        return f"{a.username}@{a.name or a.url.host}"

    async def _watch_main(self, accounts: List[EmbyAccount], instant: bool = False):
        if not accounts:
            return None
        logger.info("开始执行 Emby 保活.")
        tasks = []
        sem = asyncio.Semaphore(config.emby.concurrency or 100000)

        ctx = RunContext.prepare(description="使用全局设置的 Emby 统一保活")
        ctx.start(RunStatus.INITIALIZING)

        async def watch_wrapper(account: EmbyAccount, sem):
            async with sem:
                try:
                    emby = Emby(account)
                except Exception:
                    logger.error(f"初始化失败: {e}")
                    show_exception(e, regular=False)
                    return account, False
                if not instant:
                    wait = random.uniform(180, 360)
                    emby.log.info(f"播放视频前随机等待 {wait:.0f} 秒.")
                    await asyncio.sleep(wait)
                try:
                    emby.log.info(f"正在登陆并获取首页视频项目.")
                    if not emby.user_id:
                        if not await emby.login():
                            emby.log.warning(f"保活失败: 无法登陆.")
                            return account, False
                    await emby.load_main_page()
                    if not emby.items:
                        emby.log.warning("保活失败: 无法获取首页中的视频项目")
                        return account, False
                    else:
                        emby.log.info(f"成功登陆, 获取了 {len(emby.items)} 个首页视频项目.")
                    await asyncio.sleep(random.uniform(2, 5))
                    return account, await emby.watch()
                except EmbyError as e:
                    emby.log.warning(f"保活失败: {e}.")
                    return account, False
                except Exception as e:
                    emby.log.warning(f"保活失败: {e}")
                    show_exception(e, regular=False)
                    return account, False

        for account in accounts:
            if account.enabled:
                tasks.append(watch_wrapper(account, sem))

        failed_accounts = []
        successful_accounts = []
        results = await asyncio.gather(*tasks)
        for a, success in results:
            if success:
                successful_accounts.append(self.get_spec(a))
            else:
                failed_accounts.append(self.get_spec(a))
        fails = len(failed_accounts)

        if fails:
            if len(accounts) == 1:
                logger.error(f"保活失败: {', '.join(failed_accounts)}")
            else:
                logger.error(f"保活失败 ({fails}/{len(tasks)}): {', '.join(failed_accounts)}")
            return ctx.finish(RunStatus.FAIL, f"保活失败")
        if len(accounts) == 1:
            logger.bind(log=True).info(f"保活成功: {', '.join(successful_accounts)}.")
        else:
            logger.bind(log=True).info(
                f"保活成功 ({len(tasks)}/{len(tasks)}): {', '.join(successful_accounts)}."
            )
        return ctx.finish(RunStatus.SUCCESS, f"保活成功")

    async def run_all(self, instant: bool = False):
        return await self._watch_main(config.emby.account, instant)
