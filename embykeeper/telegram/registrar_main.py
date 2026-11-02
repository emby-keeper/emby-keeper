from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Dict, List, Type
import random
import string
import re

from loguru import logger

from embykeeper.schedule import Scheduler
from embykeeper.schema import TelegramAccount
from embykeeper.config import config
from embykeeper.runinfo import RunContext, RunStatus
from embykeeper.utils import show_exception

from .pyrogram import Client
from .embyboss import EmbybossRegister
from .dynamic import extract, get_cls
from .link import Link
from .session import ClientsSession

logger = logger.bind(scheme="teleregistrar")


class RegisterManager:
    """注册管理器"""

    def __init__(self):
        self._tasks: Dict[str, asyncio.Task] = {}
        self._schedulers: Dict[str, Scheduler] = {}
        self._scheduler_tasks: Dict[str, asyncio.Task] = {}
        self._keepalive = asyncio.Event()

        config.on_list_change("telegram.account", self._handle_account_change)
        config.on_change("registrar", self._handle_config_change)
        config.on_change("site.registrar", self._handle_config_change)

    def _module_enabled(self):
        return bool(config.registrar.enabled) if config.registrar else True

    def _track_task(self, task_key: str, task: asyncio.Task):
        existing = self._tasks.get(task_key)
        if existing and existing is not task and not existing.done():
            existing.cancel()

        self._tasks[task_key] = task

        def on_done(t: asyncio.Task, key: str = task_key):
            if self._tasks.get(key) is t:
                del self._tasks[key]
            try:
                t.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"任务 {key} 的 Telegram 注册运行任务发生错误, 该任务已停止.")
                show_exception(e, regular=False)

        task.add_done_callback(on_done)
        return task

    def _track_scheduler(self, scheduler_key: str, scheduler: Scheduler):
        existing = self._scheduler_tasks.get(scheduler_key)
        if existing and not existing.done():
            existing.cancel()

        self._schedulers[scheduler_key] = scheduler
        task = asyncio.create_task(scheduler.schedule(), name=f"Telegram 注册调度 {scheduler_key}")
        self._scheduler_tasks[scheduler_key] = task

        def on_done(t: asyncio.Task, key: str = scheduler_key):
            if self._scheduler_tasks.get(key) is t:
                del self._scheduler_tasks[key]
            if self._schedulers.get(key) is scheduler:
                del self._schedulers[key]
            try:
                t.result()
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"任务 {key} 的 Telegram 注册调度发生错误, 该调度已停止.")
                show_exception(e, regular=False)

        task.add_done_callback(on_done)
        return task

    def _handle_config_change(self, *args):
        self.stop_all()

        if not self._module_enabled():
            logger.info("已根据新的配置停止所有注册任务.")
            return

        scheduled = False
        for account in config.telegram.account:
            if account.enabled and getattr(account, "registrar", False):
                if self.schedule_account(account):
                    scheduled = True

        if scheduled:
            logger.info("已根据新的配置重新安排所有注册任务.")
        else:
            logger.info("没有需要执行的 Telegram 机器人注册任务")

    def _handle_account_change(self, added: List[TelegramAccount], removed: List[TelegramAccount]):
        for account in removed:
            self.stop_account(account.phone)
            logger.info(f"{account.phone} 账号的注册及其计划任务已被清除.")

        for account in added:
            if self._module_enabled() and account.enabled and getattr(account, "registrar", False):
                if self.schedule_account(account):
                    logger.info(f"新增的 {account.phone} 账号的注册计划任务已增加.")

    def stop_account(self, phone: str):
        task_keys = [key for key in list(self._tasks.keys()) if key == phone or key.startswith(f"{phone}.")]
        for key in task_keys:
            task = self._tasks.pop(key, None)
            if task:
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

    def stop_all(self):
        phones = set(key.split(".", 1)[0] for key in self._tasks.keys())
        phones.update(key.split(".", 1)[0] for key in self._schedulers.keys())
        phones.update(key.split(".", 1)[0] for key in self._scheduler_tasks.keys())

        for phone in phones:
            self.stop_account(phone)

    def get_sites_for_account(self, account: TelegramAccount) -> List[str]:
        phone_masked = TelegramAccount.get_phone_masked(account.phone)

        sites = []
        if account.site and account.site.registrar is not None:
            sites = account.site.registrar
        elif config.site and config.site.registrar is not None:
            sites = config.site.registrar

        if not sites:
            logger.warning(f"{phone_masked} 账号未配置 registrar 站点, 将跳过注册调度")
            return []

        return sites

    def schedule_account(self, account: TelegramAccount) -> bool:
        if (
            (not self._module_enabled())
            or (not account.enabled)
            or (not getattr(account, "registrar", False))
        ):
            return False

        self.stop_account(account.phone)

        sites_to_register_names = self.get_sites_for_account(account)
        if not sites_to_register_names:
            return False

        clses = extract(get_cls("registrar", names=sites_to_register_names))
        if not clses:
            logger.warning(f"{account.phone} 账号没有有效的 registrar 站点, 将跳过注册调度")
            return False

        scheduled = False
        for cls in clses:
            if hasattr(cls, "templ_name"):
                site_name = cls.templ_name
            else:
                site_name = cls.__module__.rsplit(".", 1)[-1]

            config_to_use = account.registrar_config or config.registrar
            site_config = config_to_use.get_site_config(site_name)
            if not site_config:
                logger.warning(f"{account.phone} 账号的站点 {site_name} 未配置注册设置, 将跳过")
                continue

            if site_config.get("times"):
                schedulers = self._schedule_site_timed(account, site_name, site_config)
                for scheduler_key, scheduler in schedulers:
                    self._track_scheduler(scheduler_key, scheduler)
                    scheduled = True
            elif site_config.get("interval_minutes"):
                task = self._schedule_site_interval(account, site_name, site_config)
                if task:
                    scheduled = True

        return scheduled

    def _schedule_site_timed(self, account: TelegramAccount, site_name: str, site_config: dict):
        phone_masked = TelegramAccount.get_phone_masked(account.phone)
        raw_times = site_config.get("times", [])
        times = raw_times if isinstance(raw_times, (list, tuple)) else [raw_times]
        times = list(dict.fromkeys(str(value).strip() for value in times if str(value).strip()))
        schedulers = []

        for index, time_value in enumerate(times):
            task_key = f"{account.phone}.{site_name}.timed.{index}"

            def on_next_time(t: datetime, scheduled_time: str = time_value):
                logger.info(
                    f'下一次 "{phone_masked}" 账号 {site_name} 站点的注册将在 {t:%m-%d} {scheduled_time} 进行.'
                )
                date_ctx = RunContext.get_or_create(f"registrar.date.{t:%Y%m%d}")
                account_ctx = RunContext.get_or_create(f"registrar.account.{account.phone}")
                site_ctx = RunContext.get_or_create(f"registrar.site.{site_name}")
                return RunContext.prepare(
                    description=f"{account.phone} 账号 {site_name} 站点定时注册 ({scheduled_time})",
                    parent_ids=[account_ctx.id, date_ctx.id, site_ctx.id],
                )

            def func(ctx: RunContext, scheduled_time: str = time_value, key: str = task_key):
                task = asyncio.create_task(
                    self._run_single_site(ctx, account, site_name, site_config),
                    name=f"Telegram 注册任务 {key}",
                )
                logger.bind(username=f"@{site_name}", name=f"{phone_masked}").info(
                    f"已计划定时抢注任务, 执行时间: {scheduled_time}"
                )
                return self._track_task(key, task)

            scheduler = Scheduler(
                func=func,
                days=1,
                start_time=time_value,
                end_time=time_value,
                on_next_time=on_next_time,
                description=f"{account.phone} 账号 {site_name} 站点定时注册 ({time_value})",
                sid=f"registrar.timed.{account.phone}.{site_name}.{index}.{time_value}",
            )
            schedulers.append((task_key, scheduler))

        return schedulers

    def _schedule_site_interval(self, account: TelegramAccount, site_name: str, site_config: dict):
        interval_minutes = site_config.get("interval_minutes")
        task_key = f"{account.phone}.{site_name}.interval"

        if interval_minutes < 3:
            task = asyncio.create_task(
                self._continuous_register_task(account, site_name, site_config),
                name=f"Telegram 连续注册任务 {task_key}",
            )
        else:
            task = asyncio.create_task(
                self._interval_register_task(account, site_name, site_config, interval_minutes),
                name=f"Telegram 间隔注册任务 {task_key}",
            )

        return self._track_task(task_key, task)

    async def _continuous_register_task(self, account: TelegramAccount, site_name: str, site_config: dict):
        interval_minutes = site_config.get("interval_minutes")

        async with ClientsSession([account]) as clients:
            async for _, client in clients:
                match = re.match(r"templ_a<(.+?)>", site_name)
                if not match:
                    logger.error(f"无法从 {site_name} 中提取机器人用户名")
                    return
                bot_username = match.group(1)

                log = logger.bind(name=f"{client.me.full_name}, @{bot_username}")
                log.info(f"开始连续注册, 间隔 {interval_minutes} 分钟.")

                if not await Link(client).auth("registrar", log_func=log.error):
                    log.error("账户权限验证失败.")
                    return

                embyboss_register = EmbybossRegister(
                    client=client,
                    logger=log,
                    username=client.me.username or f"user_{client.me.id}",
                    password="".join(random.choices(string.ascii_letters + string.digits, k=4)),
                )

                async def long_running_task():
                    try:
                        await embyboss_register.run_continuous(bot_username, interval_minutes * 60)
                    except asyncio.CancelledError:
                        log.info("连续注册任务被取消.")
                        raise
                    except Exception as e:
                        log.error(f"连续注册任务出现异常: {e}")
                        logger.exception("详细异常信息:")

                task = asyncio.create_task(long_running_task())
                client.stop_handlers.append(task.cancel)
                try:
                    await task
                finally:
                    if task.cancel in client.stop_handlers:
                        client.stop_handlers.remove(task.cancel)

    async def _interval_register_task(
        self, account: TelegramAccount, site_name: str, site_config: dict, interval_minutes: int
    ):
        phone_masked = TelegramAccount.get_phone_masked(account.phone)

        async with ClientsSession([account]) as clients:
            async for _, client in clients:
                match = re.match(r"templ_a<(.+?)>", site_name)
                bot_username = match.group(1) if match else site_name

                log = logger.bind(name=f"{client.me.full_name}, @{bot_username}")

                while True:
                    try:
                        account_ctx = RunContext.get_or_create(f"register.account.{account.phone}")
                        site_ctx = RunContext.get_or_create(f"register.site.{site_name}")
                        ctx = RunContext.prepare(
                            description=f"{client.me.full_name} 账号 {site_name} 站点间隔注册",
                            parent_ids=[account_ctx.id, site_ctx.id],
                        )

                        await self._run_single_site(ctx, account, site_name, site_config)
                        await asyncio.sleep(interval_minutes * 60)
                    except asyncio.CancelledError:
                        break
                    except Exception as e:
                        logger.error(f"{phone_masked} 账号 {site_name} 站点注册异常: {e}")
                        await asyncio.sleep(interval_minutes * 60)

    async def _run_single_site(
        self, ctx: RunContext, account: TelegramAccount, site_name: str, site_config: dict
    ):
        async with ClientsSession([account]) as clients:
            async for _, client in clients:
                match = re.match(r"templ_a<(.+?)>", site_name)
                bot_username = match.group(1) if match else site_name

                log = logger.bind(name=f"{client.me.full_name}, @{bot_username}")

                if not await Link(client).auth("registrar", log_func=log.error):
                    return

                cls = get_cls("registrar", names=[site_name])[0]

                register = cls(
                    client,
                    context=ctx,
                    retries=site_config.get("retries", 1),
                    timeout=site_config.get("timeout", 120),
                    config=site_config,
                )

                result = await register._start()
                if result.status == RunStatus.SUCCESS:
                    logger.bind(username=f"@{site_name}", name=f"{client.me.full_name}").info("注册成功")
                elif result.status == RunStatus.IGNORE:
                    logger.bind(username=f"@{site_name}", name=f"{client.me.full_name}").info("跳过注册")
                else:
                    logger.bind(username=f"@{site_name}", name=f"{client.me.full_name}").warning("注册失败")

    async def start(self):
        self._handle_config_change()

        try:
            await self._keepalive.wait()
        except asyncio.CancelledError:
            self.stop_all()
            raise

    async def run_account(self, ctx: RunContext, account: TelegramAccount, instant: bool = False):
        async with ClientsSession([account]) as clients:
            async for a, client in clients:
                await self._run_account(ctx, a, client, instant)

    async def _run_account(
        self, ctx: RunContext, account: TelegramAccount, client: Client, instant: bool = False
    ):
        log = logger.bind(username=client.me.full_name)

        site = None
        if account.site and account.site.registrar is not None:
            site = account.site.registrar
        elif config.site and config.site.registrar is not None:
            site = config.site.registrar
        else:
            log.warning("没有配置registrar站点, 注册将跳过.")
            return

        clses: List[Type] = extract(get_cls("registrar", names=site))

        if not clses:
            log.warning("没有任何有效注册站点, 注册将跳过.")
            return

        if not await Link(client).auth("registrar", log_func=log.error):
            return

        config_to_use = account.registrar_config or config.registrar
        sem = asyncio.Semaphore(config_to_use.concurrency)
        registers = []

        for cls in clses:
            if hasattr(cls, "templ_name"):
                site_name = cls.templ_name
            else:
                site_name = cls.__module__.rsplit(".", 1)[-1]

            site_config = config_to_use.get_site_config(site_name)
            if not site_config:
                log.warning(f"站点 {site_name} 未配置注册设置, 将跳过")
                continue

            site_ctx = RunContext.prepare(f"{site_name} 站点注册", parent_ids=ctx.id)
            registers.append(
                cls(
                    client,
                    context=site_ctx,
                    retries=site_config.get("retries", 1),
                    timeout=site_config.get("timeout", 120),
                    config=site_config,
                )
            )

        if not registers:
            log.warning("所有站点都未正确配置, 注册将跳过.")
            return

        tasks = []
        names = []
        for r in registers:
            names.append(f"@{r.bot_username}" if hasattr(r, "bot_username") and r.bot_username else r.name)
            tasks.append(self._task_main(r, sem))

        if names:
            logger.info(f'已启用注册器: {", ".join(names)}')

        results = await asyncio.gather(*tasks)

        failed = []
        successful = []
        ignored = []

        for r, result in results:
            if result.status == RunStatus.SUCCESS:
                successful.append(r.name)
            elif result.status == RunStatus.IGNORE:
                ignored.append(r.name)
            else:
                failed.append(r.name)

        spec = f"共{len(successful) + len(failed) + len(ignored)}个"
        if successful:
            spec += f", {len(successful)}成功"
        if failed:
            spec += f", {len(failed)}失败"
        if ignored:
            spec += f", {len(ignored)}跳过"

        if failed:
            msg = "注册部分失败" if successful else "注册失败"
            logger.bind(username=client.me.full_name).error(f"{msg} ({spec}): {', '.join(failed)}")
        else:
            logger.bind(username=client.me.full_name).info(f"注册完成 ({spec}).")

    async def _task_main(self, register, sem: asyncio.Semaphore):
        async with sem:
            result = await register._start()
            return register, result

    async def run_all(self, instant: bool = False):
        if not self._module_enabled():
            return None

        accounts = [a for a in config.telegram.account if a.enabled and getattr(a, "registrar", False)]
        tasks = [
            asyncio.create_task(self.run_account(RunContext.prepare("运行全部注册器"), account, instant))
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

    async def run_single_bot(self, bot_username: str, instant: bool = True):
        accounts = [a for a in config.telegram.account if a.enabled]

        if not accounts:
            logger.error("没有可用的Telegram账号")
            return

        tasks = []
        for account in accounts:
            tasks.append(asyncio.create_task(self._run_single_bot_for_account(account, bot_username)))

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _run_single_bot_for_account(self, account: TelegramAccount, bot_username: str):
        async with ClientsSession([account]) as clients:
            async for _, client in clients:
                log = logger.bind(name=f"{client.me.full_name}, @{bot_username}")

                if not await Link(client).auth("registrar", log_func=log.error):
                    return

                embyboss_register = EmbybossRegister(
                    client=client,
                    logger=log,
                    username=client.me.username or f"user_{client.me.id}",
                    password="".join(random.choices(string.ascii_letters + string.digits, k=4)),
                )

                task = asyncio.create_task(embyboss_register.run_continuous(bot_username, 1))
                client.stop_handlers.append(task.cancel)
                try:
                    await task
                finally:
                    if task.cancel in client.stop_handlers:
                        client.stop_handlers.remove(task.cancel)
                logger.bind(name=f"{client.me.full_name}, @{bot_username}").info("快速抢注任务已完成.")
