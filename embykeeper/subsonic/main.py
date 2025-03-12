from __future__ import annotations

import asyncio
import random
from typing import List
from loguru import logger

from embykeeper.config import config
from embykeeper.runinfo import RunContext, RunStatus
from embykeeper.schedule import Scheduler
from embykeeper.schema import SubsonicAccount
from embykeeper.utils import show_exception

from .player import SubsonicPlayer

logger = logger.bind(scheme="subsonic")


class SubsonicManager:
    def get_spec(self, a: SubsonicAccount):
        return f"{a.username}@{a.name or a.url.host}"

    async def _listen_main(self, accounts: List[SubsonicAccount], instant: bool = False):
        if not accounts:
            return None
        logger.info("开始执行 Subsonic 保活.")
        tasks = []
        sem = asyncio.Semaphore(config.subsonic.concurrency or 100000)

        ctx = RunContext.prepare(description="使用全局设置的 Subsonic 统一保活")
        ctx.start(RunStatus.INITIALIZING)

        async def watch_wrapper(account: SubsonicAccount, sem):
            async with sem:
                try:
                    player = SubsonicPlayer(account)
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
        return await self._listen_main(config.subsonic.account, instant)

    async def schedule_all(self, instant: bool = False):
        unified_accounts: List[SubsonicAccount] = []
        independent_accounts: List[SubsonicAccount] = []
        tasks = []

        # Separate accounts into global and site-specific
        for account in config.subsonic.account:
            if not account.enabled:
                continue
            if account.time_range or account.interval_days:
                independent_accounts.append(account)
            else:
                unified_accounts.append(account)

        # Schedule global accounts together
        if unified_accounts:
            on_next_time = lambda t: logger.bind(log=True).info(
                f"下一次 Subsonic 保活将在 {t.strftime('%m-%d %H:%M %p')} 进行."
            )
            scheduler = Scheduler.from_str(
                func=lambda ctx: self._listen_main(unified_accounts, instant),
                interval_days=config.emby.interval_days,
                time_range=config.emby.time_range,
                on_next_time=on_next_time,
                sid="subsonic.watch.global",
                description="Subsonic 保活任务",
            )
            tasks.append(scheduler.schedule())

        # Schedule individual site accounts
        for account in independent_accounts:
            account_spec = self.get_spec(account)
            time_range = account.time_range or config.emby.time_range
            interval = account.interval_days or config.emby.interval_days

            # 创建一个函数来生成 on_next_time 回调，确保每个账号都有自己的 account_spec
            def make_on_next_time(spec):
                return lambda t: logger.bind(log=True).info(
                    f"下一次 Subsonic 账号 ({spec}) 的保活将在 {t.strftime('%m-%d %H:%M %p')} 进行."
                )

            scheduler = Scheduler.from_str(
                func=lambda ctx: self._watch_main([account], False),
                interval_days=interval,
                time_range=time_range,
                on_next_time=make_on_next_time(account_spec),  # 使用工厂函数创建回调
                sid=f"subsonic.watch.{account_spec}",
                description=f"Subsonic 保活任务 - {account_spec}",
            )
            tasks.append(scheduler.schedule())

        if not tasks:
            logger.info("没有需要执行的 Subsonic 保活任务")
            return None

        await asyncio.gather(*tasks)
