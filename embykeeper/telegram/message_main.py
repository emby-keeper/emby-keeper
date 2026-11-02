from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type

from loguru import logger

from embykeeper.schema import TelegramAccount
from embykeeper.config import config
from embykeeper.runinfo import RunContext
from embykeeper.utils import show_exception

from .messager import Messager
from .dynamic import extract, get_cls, get_names
from .link import Link
from .session import ClientsSession
from .pyrogram import Client

logger = logger.bind(scheme="telechecker")


@dataclass
class _MessageSpec:
    key: str
    site_name: str
    cls: Type[Messager]


@dataclass
class _AccountState:
    account: TelegramAccount
    task: Optional[asyncio.Task] = None
    reconcile_event: asyncio.Event = field(default_factory=asyncio.Event)
    site_tasks: Dict[str, asyncio.Task] = field(default_factory=dict)
    force_site_refresh: bool = True


class MessageManager:
    def __init__(self):
        self._accounts: Dict[str, _AccountState] = {}
        self._reconcile_lock = asyncio.Lock()
        self._reconcile_task: Optional[asyncio.Task] = None
        self._reconcile_dirty = False
        self._force_site_refresh = False

        config.on_list_change("telegram.account", self._handle_account_change)
        config.on_change("messager", self._handle_config_change)
        config.on_change("site.messager", self._handle_site_change)

    def _module_enabled(self):
        return bool(config.messager.enabled) if config.messager else True

    @staticmethod
    def _account_signature(account: TelegramAccount):
        return (account.phone, account.api_id, account.api_hash, account.session)

    def _resolve_site_names(self, account: TelegramAccount):
        if account.site and account.site.messager is not None:
            return account.site.messager
        if config.site and config.site.messager is not None:
            return config.site.messager
        return get_names("messager")

    @staticmethod
    def _get_site_name(cls: Type[Messager]):
        if hasattr(cls, "templ_name"):
            return cls.templ_name
        return cls.__module__.rsplit(".", 1)[-1]

    def _build_message_specs(self, account: TelegramAccount):
        site_names = self._resolve_site_names(account)
        clses: List[Type[Messager]] = extract(get_cls("messager", names=site_names))

        specs = []
        for cls in clses:
            site_name = self._get_site_name(cls)
            key = f"{site_name}:{cls.__module__}.{cls.__qualname__}"
            specs.append(_MessageSpec(key=key, site_name=site_name, cls=cls))

        return specs, site_names

    def _request_reconcile(self, force_site_refresh: bool = False):
        if force_site_refresh:
            self._force_site_refresh = True
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
        self._force_site_refresh = False

    async def _run_reconcile_loop(self):
        try:
            async with self._reconcile_lock:
                while self._reconcile_dirty:
                    self._reconcile_dirty = False
                    force_site_refresh = self._force_site_refresh
                    self._force_site_refresh = False
                    await self._reconcile(force_site_refresh=force_site_refresh)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("根据新的配置更新 Telegram 自动水群任务时出错.")
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
        return {a.phone: a for a in accounts if a.enabled and a.messager}

    async def _reconcile(self, force_site_refresh: bool = False):
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
            logger.info("已根据新的配置停止所有 Telegram 自动水群任务.")
            return

        if not desired_accounts:
            logger.info("没有需要执行的 Telegram 自动水群任务")
            return

        for phone, account in desired_accounts.items():
            state = self._accounts.get(phone)
            if not state:
                self.start_account(account)
                state = self._accounts.get(phone)
            if not state:
                continue

            state.account = account
            if force_site_refresh:
                state.force_site_refresh = True
            state.reconcile_event.set()

        logger.info("已根据新的配置收敛 Telegram 自动水群任务.")

    async def _stop_accounts(self, phones):
        tasks = []
        for phone in phones:
            state = self._accounts.pop(phone, None)
            if not state or not state.task:
                continue
            state.task.cancel()
            tasks.append(state.task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _on_task_done(self, phone: str, task: asyncio.Task):
        state = self._accounts.get(phone)
        if state and state.task is task:
            del self._accounts[phone]

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"账户 {phone} 的自动水群任务发生错误, 自动水群已停止.")
            show_exception(e, regular=False)

    def _handle_config_change(self, *args):
        self._request_reconcile(force_site_refresh=True)

    def _handle_site_change(self, *args):
        self._request_reconcile()

    def _handle_account_change(self, added: List[TelegramAccount], removed: List[TelegramAccount]):
        self._request_reconcile()

    def stop_all(self):
        self._cancel_reconcile_task()
        for phone in list(self._accounts.keys()):
            self.stop_account(phone)

    def stop_account(self, phone: str):
        state = self._accounts.pop(phone, None)
        if state and state.task:
            state.task.cancel()

    def start_account(self, account: TelegramAccount):
        if not self._module_enabled() or not account.enabled or not account.messager:
            return

        state = self._accounts.get(account.phone)
        if state and state.task and not state.task.done():
            return state.task

        state = _AccountState(account=account)
        task = asyncio.create_task(self.run_account(state), name=f"messager:{account.phone}")
        state.task = task
        task.add_done_callback(lambda t, phone=account.phone: self._on_task_done(phone, t))
        self._accounts[account.phone] = state
        return task

    async def _cancel_site_tasks(self, state: _AccountState, keys=None):
        selected = list(keys if keys is not None else state.site_tasks.keys())
        tasks = []

        for key in selected:
            task = state.site_tasks.pop(key, None)
            if not task:
                continue
            if not task.done():
                task.cancel()
                tasks.append(task)

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _on_site_task_done(self, phone: str, key: str, task: asyncio.Task):
        state = self._accounts.get(phone)
        if state and state.site_tasks.get(key) is task:
            del state.site_tasks[key]

        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning(f"账户 {phone} 的自动水群站点任务发生错误, 该站点自动水群已停止.")
            show_exception(e, regular=False)

    def _start_site_task(self, state: _AccountState, ctx: RunContext, client: Client, spec: _MessageSpec):
        site_ctx = RunContext.prepare(f"{spec.site_name} 站点自动水群", parent_ids=ctx.id)
        messager = spec.cls(
            account=state.account,
            me=client.me,
            context=site_ctx,
            config=config.messager.get_site_config(spec.site_name) if config.messager else {},
        )
        task = asyncio.create_task(messager._start(), name=f"messager:{state.account.phone}:{spec.key}")
        task.add_done_callback(
            lambda t, phone=state.account.phone, key=spec.key: self._on_site_task_done(phone, key, t)
        )
        state.site_tasks[spec.key] = task
        return messager.name or spec.site_name

    async def run_account(self, state: _AccountState):
        phone = state.account.phone
        account_ctx = RunContext.get_or_create(f"messager.account.{phone}")
        try:
            async with ClientsSession([state.account]) as clients:
                async for _, client in clients:
                    await RunContext.run(
                        lambda c: self._run_account(state, c, client),
                        description=f"{phone} 账号自动水群",
                        parent_ids=[account_ctx.id],
                    )
        finally:
            await self._cancel_site_tasks(state)

    async def _run_account(self, state: _AccountState, ctx: RunContext, client: Client):
        log = logger.bind(username=client.me.full_name)

        if not await Link(client).auth("messager", log_func=log.error):
            return

        state.reconcile_event.set()
        while True:
            await state.reconcile_event.wait()
            state.reconcile_event.clear()
            await self._reconcile_account(state, ctx, client, log)

    async def _reconcile_account(self, state: _AccountState, ctx: RunContext, client: Client, log):
        specs, site_names = self._build_message_specs(state.account)

        if state.force_site_refresh:
            await self._cancel_site_tasks(state)
            state.force_site_refresh = False

        if not specs:
            if site_names is not None:
                log.warning("没有任何有效自动水群站点, 自动水群将跳过.")
            return

        desired_keys = {spec.key for spec in specs}
        removed_keys = [key for key in state.site_tasks.keys() if key not in desired_keys]
        if removed_keys:
            await self._cancel_site_tasks(state, removed_keys)

        started_names = []
        for spec in specs:
            if spec.key in state.site_tasks:
                continue
            started_names.append(self._start_site_task(state, ctx, client, spec))

        if started_names:
            log.debug(f'已启用自动水群器: {", ".join(started_names)}')

    async def run_all(self):
        task = self._request_reconcile(force_site_refresh=True)
        if task:
            await task

        tasks = [state.task for state in self._accounts.values() if state.task]
        if tasks:
            await asyncio.gather(*tasks)
