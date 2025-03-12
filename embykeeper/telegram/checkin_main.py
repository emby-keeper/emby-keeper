from __future__ import annotations

import asyncio
from datetime import datetime
import random
from typing import List, Dict, Set, Tuple, Type

from loguru import logger

from embykeeper.schedule import Scheduler
from embykeeper.schema import TelegramAccount
from embykeeper.config import config
from embykeeper.runinfo import RunContext, RunStatus
from embykeeper.utils import AsyncTaskPool, show_exception

from .checkiner import BaseBotCheckin
from .dynamic import extract, get_cls, get_names
from .link import Link
from .session import ClientsSession
from .pyrogram import Client

logger = logger.bind(scheme="telechecker")


class CheckinerManager:
    """签到管理器"""

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}  # phone -> task
        self._site_tasks: Dict[str, Dict[str, asyncio.Task]] = {}  # phone -> site -> task
        self._schedulers: Dict[str, Scheduler] = {}  # phone -> scheduler
        self._pool = AsyncTaskPool()

        config.on_list_change("telegram.account", self._handle_account_change)

    def _handle_account_change(self, added: List[TelegramAccount], removed: List[TelegramAccount]):
        """Handle account additions and removals"""
        for account in removed:
            self.stop_account(account.phone)
            logger.info(f"{account.phone} 账号的签到及其计划任务已被清除.")

        for account in added:
            scheduler = self.schedule_account(account)
            self._pool.add(scheduler.schedule())
            logger.info(f"新增的 {account.phone} 账号的计划任务已增加.")

    def stop_account(self, phone: str):
        """Stop scheduling and running tasks for an account"""
        # Cancel main checkin task
        if phone in self._tasks:
            self._tasks[phone].cancel()
            del self._tasks[phone]

        # Cancel all site-specific tasks
        if phone in self._site_tasks:
            for task in self._site_tasks[phone].values():
                task.cancel()
            del self._site_tasks[phone]

        if phone in self._schedulers:
            del self._schedulers[phone]

    def schedule_account(self, account: TelegramAccount):
        """Schedule checkins for an account"""
        if (not account.checkiner) or (not account.enabled):
            return

        # Use account-specific config if available, otherwise use global
        config_to_use = account.checkiner_config or config.checkiner

        def on_next_time(t: datetime):
            logger.info(f"下一次 {account.phone} 账号的签到将在 {t.strftime('%m-%d %H:%M %p')} 进行.")
            date_ctx = RunContext.get_or_create(f"checkiner.date.{t.strftime('%Y%m%d')}")
            account_ctx = RunContext.get_or_create(f"checkiner.account.{account.phone}")
            return RunContext.prepare(
                description=f"{account.phone} 账号签到",
                parent_ids=[account_ctx.id, date_ctx.id],
            )

        def func(ctx: RunContext):
            if account.phone in self._tasks:
                self._tasks[account.phone].cancel()
                del self._tasks[account.phone]
            task = self._tasks[account.phone] = asyncio.create_task(self.run_account(ctx, account))
            return task

        scheduler = Scheduler.from_str(
            func=func,
            interval_days=config_to_use.interval_days,
            time_range=config_to_use.time_range,
            on_next_time=on_next_time,
            description=f"{account.phone} 每日签到定时任务",
            sid=f"checkiner.{account.phone}",
        )
        self._schedulers[account.phone] = scheduler
        return scheduler

    async def _task_main(self, checkiner: BaseBotCheckin, sem: asyncio.Semaphore, wait=0):
        if config.debug_cron:
            wait = 0.1
        if wait > 0:
            checkiner.log.debug(f"随机启动等待: 将等待 {wait:.2f} 分钟以启动.")
        await asyncio.sleep(wait * 60)
        async with sem:
            result = await checkiner._start()
            return checkiner, result

    async def run_account(self, ctx: RunContext, account: TelegramAccount, instant: bool = False):
        """Run checkin for a single account"""
        async with ClientsSession([account]) as clients:
            async for a, client in clients:
                await self._run_account(ctx, a, client, instant)

    def schedule_reschedule(
        self, ctx: RunContext, at: datetime, account: TelegramAccount, site: str
    ) -> asyncio.Task:
        try:
            account_ctx = RunContext.get_or_create(f"checkiner.account.{account.phone}")
            site_ctx = RunContext.prepare(
                description=f"{account.phone} 账号 {site} 站点重新签到", parent_ids=[account_ctx.id, ctx.id]
            )
            site_ctx.reschedule = (ctx.reschedule or 0) + 1

            async def _schedule():
                # 计算延迟时间(秒)
                delay = (at - datetime.now()).total_seconds()
                if delay > 0:
                    logger.debug(
                        f"已安排账户 {account.phone} 的 {site} 站点在 {at.strftime('%m-%d %H:%M %p')} 重新尝试签到."
                    )
                    await asyncio.sleep(delay)
                if account.phone in self._site_tasks and site in self._site_tasks[account.phone]:
                    self._site_tasks[account.phone][site].cancel()
                    del self._site_tasks[account.phone][site]
                await self._run_single_site(site_ctx, account, site)

            task = asyncio.create_task(_schedule())
            # Initialize _site_tasks for this phone if it doesn't exist
            if account.phone not in self._site_tasks:
                self._site_tasks[account.phone] = {}
            # Store the task
            self._site_tasks[account.phone][site] = task
            return task
        except Exception as e:
            logger.warning(f"重新安排 {site} 站点签到时间失败: {e}")
            show_exception(e, regular=False)

    async def _run_single_site(self, ctx: RunContext, account: TelegramAccount, site_name: str):
        async with ClientsSession([account]) as clients:
            async for _, client in clients:
                cls = get_cls("checkiner", names=[site_name])[0]
                config_to_use = account.checkiner_config or config.checkiner

                c: BaseBotCheckin = cls(
                    client,
                    context=ctx,
                    retries=config_to_use.retries,
                    timeout=config_to_use.timeout,
                    config=config_to_use.get_site_config(site_name),
                )

                log = logger.bind(username=client.me.name, name=c.name)

                result = await c._start()
                if result.status == RunStatus.SUCCESS:
                    log.info("重新签到成功.")
                elif result.status == RunStatus.NONEED:
                    log.info("多次重新签到后依然为已签到状态, 已跳过.")
                elif result.status == RunStatus.RESCHEDULE:
                    if c.ctx.next_time:
                        log.debug("继续等待重新签到.")
                        self.schedule_reschedule(ctx, c.ctx.next_time, account, site_name)
                else:
                    log.debug("站点重新签到失败.")

    async def _run_account(
        self, ctx: RunContext, account: TelegramAccount, client: Client, instant: bool = False
    ):
        """Run checkins for a single user"""
        log = logger.bind(username=client.me.name)

        # Get checkin classes based on account config or global config
        site = None
        if account.site and account.site.checkiner is not None:
            site = account.site.checkiner
        elif config.site and config.site.checkiner is not None:
            site = config.site.checkiner
        else:
            site = get_names("checkiner")

        clses: List[Type[BaseBotCheckin]] = extract(get_cls("checkiner", names=site))

        if not clses:
            if site is not None:  # Only show warning if sites were specified but none were valid
                log.warning("没有任何有效签到站点, 签到将跳过.")
            return

        if not await Link(client).auth("checkiner", log_func=log.error):
            return

        config_to_use = account.checkiner_config or config.checkiner
        sem = asyncio.Semaphore(config_to_use.concurrency)
        checkiners = []
        for cls in clses:
            if hasattr(cls, "templ_name"):
                site_name = cls.templ_name
            else:
                site_name = cls.__module__.rsplit(".", 1)[-1]
            site_ctx = RunContext.prepare(f"{site_name} 站点签到", parent_ids=ctx.id)
            checkiners.append(
                cls(
                    client,
                    context=site_ctx,
                    retries=config_to_use.retries,
                    timeout=config_to_use.timeout,
                    config=config_to_use.get_site_config(site_name),
                )
            )

        tasks = []
        names = []
        for c in checkiners:
            names.append(c.name)
            wait = 0 if instant else random.uniform(0, config_to_use.random_start)
            task = self._task_main(c, sem, wait)
            tasks.append(task)

        if names:
            log.info(f'已启用签到器: {", ".join(names)}')

        results: List[Tuple[BaseBotCheckin, RunContext]] = await asyncio.gather(*tasks)

        failed = []
        ignored = []
        successful = []
        checked = []

        for c, result in results:
            if result.status == RunStatus.IGNORE:
                ignored.append(c.name)
            elif result.status == RunStatus.SUCCESS:
                successful.append(c.name)
            elif result.status == RunStatus.NONEED:
                checked.append(c.name)
            elif result.status == RunStatus.RESCHEDULE:
                if hasattr(c, "templ_name"):
                    site_name = c.templ_name
                else:
                    site_name = cls.__module__.rsplit(".", 1)[-1]
                if c.ctx.next_time:
                    self.schedule_reschedule(ctx, c.ctx.next_time, account, site_name)
                checked.append(c.name)
            else:
                failed.append(c.name)

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
            msg = "签到部分失败" if successful else "签到失败"
            log.bind(log=True).error(f"{msg} ({spec}): {', '.join(failed)}")
        else:
            log.bind(log=True).info(f"签到成功 ({spec}).")

    def new_ctx(self):
        now = datetime.now()
        ctx = RunContext.get_or_create(
            f"checkiner.run.{now.timestamp()}",
            description=f"{now.strftime('%Y-%m-%d')} 签到",
        )
        return ctx

    async def run_all(self, instant: bool = False):
        """Run checkins for all enabled accounts without scheduling"""
        accounts = [a for a in config.telegram.account if a.enabled and a.checkiner]
        tasks = [
            asyncio.create_task(self.run_account(RunContext.prepare("运行全部签到器"), account, instant))
            for account in accounts
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def schedule_all(self):
        """Start scheduling checkins for all accounts"""

        for a in config.telegram.account:
            if a.enabled and a.checkiner:
                scheduler = self.schedule_account(a)
                self._pool.add(scheduler.schedule())

        if not self._schedulers:
            logger.info("没有需要执行的 Telegram 机器人签到任务")
            return None

        await self._pool.wait()
