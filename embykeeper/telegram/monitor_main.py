from __future__ import annotations

import asyncio
from typing import Dict, List, Set, Type

from loguru import logger

from embykeeper.schema import TelegramAccount
from embykeeper.config import config
from embykeeper.runinfo import RunContext

from .monitor import Monitor
from .dynamic import extract, get_cls, get_names
from .link import Link
from .session import ClientsSession
from .pyrogram import Client

logger = logger.bind(scheme="telechecker")


class MonitorManager:
    """监控管理器"""

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}  # phone -> task
        self._running: Set[str] = set()  # Currently running phones

        # Set up config change callbacks
        config.on_list_change("telegram.account", self._handle_account_change)

    def _handle_account_change(self, added: List[TelegramAccount], removed: List[TelegramAccount]):
        """Handle account additions and removals"""
        for account in removed:
            logger.info(f"{account.phone} 账号的群组监控任务已被清除.")
            self.stop_account(account.phone)

        for account in added:
            if account.monitor and account.enabled:
                logger.info(f"新增的 {account.phone} 账号的群组监控任务已增加.")
                self.start_account(account)

    def stop_account(self, phone: str):
        """Stop running tasks for an account"""
        if phone in self._tasks:
            self._tasks[phone].cancel()
            del self._tasks[phone]

        self._running.discard(phone)

    def start_account(self, account: TelegramAccount):
        """Start monitoring for an account"""
        if not account.monitor or account.phone in self._running:
            return
        task = asyncio.create_task(self.run_account(account))
        self._tasks[account.phone] = task
        return task

    async def run_account(self, account: TelegramAccount):
        """Run monitor for a single account"""
        if account.phone in self._running:
            logger.warning(f"账户 {account.phone} 的监控已经在执行.")
            return

        account_ctx = RunContext.get_or_create(f"monitor.account.{account.phone}")

        self._running.add(account.phone)
        try:
            async with ClientsSession([account]) as clients:
                async for a, client in clients:
                    await RunContext.run(
                        lambda c: self._run_account(c, a, client),
                        description=f"{account.phone} 账号监控",
                        parent_ids=[account_ctx.id],
                    )
        finally:
            self._running.discard(account.phone)

    async def _run_account(self, ctx: RunContext, account: TelegramAccount, client: Client):
        """Run monitors for a single user"""
        log = logger.bind(username=client.me.name)

        # Get monitor classes based on account config or global config
        site = None
        if account.site and account.site.monitor is not None:
            site = account.site.monitor
        elif config.site and config.site.monitor is not None:
            site = config.site.monitor
        else:
            site = get_names("monitor")

        clses: List[Type[Monitor]] = extract(get_cls("monitor", names=site))

        if not clses:
            if site is not None:  # Only show warning if sites were specified but none were valid
                log.warning("没有任何有效监控站点, 监控将跳过.")
            return

        if not await Link(client).auth("monitor", log_func=log.error):
            return

        monitors = []
        names = []

        for cls in clses:
            if hasattr(cls, "templ_name"):
                site_name = cls.templ_name
            else:
                site_name = cls.__module__.rsplit(".", 1)[-1]
            site_ctx = RunContext.prepare(f"{site_name} 站点监控", parent_ids=ctx.id)
            monitor = cls(
                client,
                context=site_ctx,
                config=config.monitor.get_site_config(site_name),
            )
            monitors.append(monitor)
            names.append(monitor.name)

        if names:
            log.debug(f'已启用监控器: {", ".join(names)}')

        # Start all monitors concurrently
        await asyncio.gather(*[m._start() for m in monitors])

    async def run_all(self):
        """Run monitoring for all enabled accounts"""
        accounts = [a for a in config.telegram.account if a.enabled and a.monitor]
        tasks = []
        for account in accounts:
            task = self.start_account(account)
            if task:  # start_account might return None if account is already running
                tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks)
