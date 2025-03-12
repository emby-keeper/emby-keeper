from __future__ import annotations

import base64
from collections import OrderedDict
from contextlib import asynccontextmanager
from datetime import datetime
import asyncio
import inspect
import os
from pathlib import Path
import sqlite3
import struct
from typing import Union
import logging

from rich.prompt import Prompt
from loguru import logger
import pyrogram
from pyrogram import raw, types, utils, filters, dispatcher
from pyrogram.enums import SentCodeType
from pyrogram.errors import (
    ChannelPrivate,
    PersistentTimestampOutdated,
    PersistentTimestampInvalid,
    BadRequest,
    SessionPasswordNeeded,
    CodeInvalid,
    PhoneCodeInvalid,
    FloodWait,
    PhoneNumberInvalid,
    PhoneNumberBanned,
    BadRequest,
    MessageIdInvalid,
)
from pyrogram.handlers import (
    MessageHandler,
    RawUpdateHandler,
    DisconnectHandler,
    EditedMessageHandler,
)
from pyrogram.storage.memory_storage import MemoryStorage
from pyrogram.storage.sqlite_storage import SQLiteStorage
from pyrogram.storage.file_storage import USERNAMES_SCHEMA, UPDATE_STATE_SCHEMA
from pyrogram.handlers.handler import Handler

from embykeeper import var, __name__ as __product__, __version__
from embykeeper.utils import async_partial, show_exception

var.tele_used.set()

logger = logger.bind(scheme="telegram")


def _name(self: Union[types.User, types.Chat]):
    return " ".join([n for n in (self.first_name, self.last_name) if n])


def _chat_name(self: types.Chat):
    if self.title:
        return self.title
    else:
        return _name(self)


setattr(types.User, "name", property(_name))
setattr(types.Chat, "name", property(_chat_name))


class LogRedirector(logging.StreamHandler):
    def emit(self, record):
        try:
            if record.levelno >= logging.WARNING:
                logger.debug(f"Pyrogram log: {record.getMessage()}")
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)


pyrogram_session_logger = logging.getLogger("pyrogram")
for h in pyrogram_session_logger.handlers[:]:
    pyrogram_session_logger.removeHandler(h)
pyrogram_session_logger.addHandler(LogRedirector())


class Dispatcher(dispatcher.Dispatcher):
    updates_count = 0

    def __init__(self, client: Client):
        super().__init__(client)
        self.mutex = asyncio.Lock()

    async def start(self):
        logger.debug("Telegram 更新分配器启动.")
        if not self.client.no_updates:

            self.handler_worker_tasks = []
            for _ in range(self.client.workers):
                self.handler_worker_tasks.append(self.loop.create_task(self.handler_worker()))

            if not self.client.skip_updates:
                await self.client.recover_gaps()

    async def stop(self, clear: bool = True):
        if not self.client.no_updates:
            for i in range(self.client.workers):
                self.updates_queue.put_nowait(None)
            for i in self.handler_worker_tasks:
                i.cancel()
                try:
                    await i
                except asyncio.CancelledError:
                    pass
            if clear:
                self.handler_worker_tasks.clear()
                self.groups.clear()

    def add_handler(self, handler, group: int):
        async def fn():
            async with self.mutex:
                if group not in self.groups:
                    self.groups[group] = []
                    self.groups = OrderedDict(sorted(self.groups.items()))
                self.groups[group].append(handler)
                # logger.debug(f"增加了 Telegram 更新处理器: {handler.__class__.__name__}.")

        return self.loop.create_task(fn())

    def remove_handler(self, handler, group: int):
        async def fn():
            async with self.mutex:
                if group not in self.groups:
                    raise ValueError(f"Group {group} does not exist. Handler was not removed.")
                self.groups[group].remove(handler)
                # logger.debug(f"移除了 Telegram 更新处理器: {handler.__class__.__name__}.")

        return self.loop.create_task(fn())

    async def handler_worker(self):
        while True:
            packet = await self.updates_queue.get()
            Dispatcher.updates_count += 1

            if packet is None:
                break

            try:
                update, users, chats = packet
                parser = self.update_parsers.get(type(update), None)

                try:
                    parsed_update, handler_type = (
                        await parser(update, users, chats) if parser is not None else (None, type(None))
                    )
                except (ValueError, BadRequest):
                    continue

                async with self.mutex:
                    groups = {i: g[:] for i, g in self.groups.items()}

                for group in groups.values():
                    for handler in group:
                        args = None

                        if isinstance(handler, handler_type):
                            try:
                                if await handler.check(self.client, parsed_update):
                                    args = (parsed_update,)
                            except Exception as e:
                                logger.warning(f"Telegram 错误: {e}")
                                continue

                        elif isinstance(handler, RawUpdateHandler):
                            try:
                                if await handler.check(self.client, update):
                                    args = (update, users, chats)
                            except Exception as e:
                                logger.debug(f"更新回调函数内发生错误.")
                                show_exception(e, regular=False)
                        if args is None:
                            continue

                        try:
                            if inspect.iscoroutinefunction(handler.callback):
                                await handler.callback(self.client, *args)
                            else:
                                await self.loop.run_in_executor(
                                    self.client.executor, handler.callback, self.client, *args
                                )
                        except pyrogram.StopPropagation:
                            raise
                        except pyrogram.ContinuePropagation:
                            continue
                        except Exception as e:
                            logger.error(f"更新回调函数内发生错误.")
                            show_exception(e, regular=False)
                        break
                    else:
                        continue
                    break
            except pyrogram.StopPropagation:
                pass
            except Exception as e:
                logger.warning("更新控制器错误.")
                show_exception(e, regular=False)


class FileStorage(SQLiteStorage):
    FILE_EXTENSION = ".session"

    def __init__(self, name: str, workdir: Path, session_string: str = None):
        super().__init__(name)

        self.database = workdir / (self.name + self.FILE_EXTENSION)
        self.session_string = session_string

    def update(self):
        version = self.version()

        if version == 1:
            with self.conn:
                self.conn.execute("DELETE FROM peers")

            version += 1

        if version == 2:
            with self.conn:
                self.conn.execute("ALTER TABLE sessions ADD api_id INTEGER")

            version += 1

        if version == 3:
            with self.conn:
                self.conn.executescript(USERNAMES_SCHEMA)

            version += 1

        if version == 4:
            with self.conn:
                self.conn.executescript(UPDATE_STATE_SCHEMA)

            version += 1

        if version == 5:
            with self.conn:
                self.conn.execute("CREATE INDEX idx_usernames_id ON usernames (id);")

            version += 1

        self.version(version)

    async def open(self):
        path = self.database
        file_exists = path.is_file()

        self.conn = sqlite3.connect(str(path), timeout=1, check_same_thread=False)

        if not file_exists:
            self.create()
            if self.session_string:
                # Old format
                if len(self.session_string) in [self.SESSION_STRING_SIZE, self.SESSION_STRING_SIZE_64]:
                    dc_id, test_mode, auth_key, user_id, is_bot = struct.unpack(
                        (
                            self.OLD_SESSION_STRING_FORMAT
                            if len(self.session_string) == self.SESSION_STRING_SIZE
                            else self.OLD_SESSION_STRING_FORMAT_64
                        ),
                        base64.urlsafe_b64decode(self.session_string + "=" * (-len(self.session_string) % 4)),
                    )

                    await self.dc_id(dc_id)
                    await self.test_mode(test_mode)
                    await self.auth_key(auth_key)
                    await self.user_id(user_id)
                    await self.is_bot(is_bot)
                    await self.date(0)

                    logger.warning(
                        "You are using an old session string format. Use export_session_string to update"
                    )
                    return

                dc_id, api_id, test_mode, auth_key, user_id, is_bot = struct.unpack(
                    self.SESSION_STRING_FORMAT,
                    base64.urlsafe_b64decode(self.session_string + "=" * (-len(self.session_string) % 4)),
                )

                await self.dc_id(dc_id)
                await self.api_id(api_id)
                await self.test_mode(test_mode)
                await self.auth_key(auth_key)
                await self.user_id(user_id)
                await self.is_bot(is_bot)
                await self.date(0)
        else:
            self.update()

        with self.conn:
            self.conn.execute("VACUUM")

    async def delete(self):
        os.remove(self.database)


class Client(pyrogram.Client):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.dispatcher = Dispatcher(self)
        self.stop_handlers = []
        if self.in_memory:
            self.storage = MemoryStorage(self.name, self.session_string)
        else:
            self.storage = FileStorage(self.name, self.workdir, self.session_string)

    async def authorize(self):
        if self.bot_token:
            return await self.sign_in_bot(self.bot_token)
        retry = False
        while True:
            try:
                sent_code = await self.send_code(self.phone_number)
                code_target = {
                    SentCodeType.APP: " Telegram 客户端",
                    SentCodeType.SMS: "短信",
                    SentCodeType.CALL: "来电",
                    SentCodeType.FLASH_CALL: "闪存呼叫",
                    SentCodeType.FRAGMENT_SMS: " Fragment 短信",
                    SentCodeType.EMAIL_CODE: "邮件",
                }
                if not self.phone_code:
                    if retry:
                        msg = f'验证码错误, 请重新输入 "{self.phone_number}" 的登录验证码 (按回车确认)'
                    else:
                        msg = f'请从{code_target[sent_code.type]}接收 "{self.phone_number}" 的登录验证码 (按回车确认)'
                    try:
                        self.phone_code = Prompt.ask(" " * 23 + msg, console=var.console)
                    except EOFError:
                        raise BadRequest(
                            f'登录 "{self.phone_number}" 时出现异常: 您正在使用非交互式终端, 无法输入验证码.'
                        )
                signed_in = await self.sign_in(self.phone_number, sent_code.phone_code_hash, self.phone_code)
            except (CodeInvalid, PhoneCodeInvalid):
                self.phone_code = None
                retry = True
            except SessionPasswordNeeded:
                retry = False
                while True:
                    if not self.password:
                        if retry:
                            msg = f'密码错误, 请重新输入 "{self.phone_number}" 的两步验证密码 (不显示, 按回车确认)'
                        else:
                            msg = f'需要输入 "{self.phone_number}" 的两步验证密码 (不显示, 按回车确认)'
                        self.password = Prompt.ask(" " * 23 + msg, password=True, console=var.console)
                    try:
                        return await self.check_password(self.password)
                    except BadRequest:
                        self.password = None
                        retry = True
            except FloodWait:
                raise BadRequest(f'登录 "{self.phone_number}" 时出现异常: 登录过于频繁.')
            except PhoneNumberInvalid:
                raise BadRequest(
                    f'登录 "{self.phone_number}" 时出现异常: 您使用了错误的手机号 (格式错误或没有注册).'
                )
            except PhoneNumberBanned:
                raise BadRequest(f'登录 "{self.phone_number}" 时出现异常: 您的账户已被封禁.')
            except Exception as e:
                logger.error(f"登录时出现异常错误!")
                show_exception(e, regular=False)
                retry = True
            else:
                break
        if isinstance(signed_in, types.User):
            return signed_in
        else:
            raise BadRequest("该账户尚未注册")

    def add_handler(self, handler: Handler, group: int = 0):
        if isinstance(handler, DisconnectHandler):
            self.disconnect_handler = handler.callback

            async def dummy():
                pass

            return asyncio.ensure_future(dummy())
        else:
            return self.dispatcher.add_handler(handler, group)

    def remove_handler(self, handler: Handler, group: int = 0):
        if isinstance(handler, DisconnectHandler):
            self.disconnect_handler = None

            async def dummy():
                pass

            return asyncio.ensure_future(dummy())
        else:
            return self.dispatcher.remove_handler(handler, group)

    async def invoke(self, query, *args, **kw):
        last_error = None
        for _ in range(3):
            try:
                return await super().invoke(query, *args, **kw)
            except OSError as e:
                last_error = e
                await asyncio.sleep(0.5)
                continue
            except (
                sqlite3.ProgrammingError
            ) as e:  # Cannot operate on a closed database. The client is stopping.
                raise asyncio.CancelledError() from None
        else:
            raise OSError(
                f"执行 Telegram 请求由于网络因素而失败, 且重试超限."
                f"({last_error.__class__.__name__} for {query.__class__.__name__})"
            )

    @asynccontextmanager
    async def catch_reply(self, chat_id: Union[int, str], outgoing=False, filter=None):
        async def handler_func(client, message, future: asyncio.Future):
            try:
                future.set_result(message)
            except asyncio.InvalidStateError:
                pass

        future = asyncio.Future()
        f = filters.chat(chat_id)
        if not outgoing:
            f = f & (~filters.outgoing)
        if filter:
            f = f & filter
        handler = MessageHandler(async_partial(handler_func, future=future), f)
        await self.add_handler(handler, group=0)
        try:
            yield future
        finally:
            await self.remove_handler(handler, group=0)

    @asynccontextmanager
    async def catch_edit(self, message: types.Message, filter=None):
        def filter_message(id: int):
            async def func(flt, _, message: types.Message):
                return message.id == id

            return filters.create(func, "MessageFilter")

        async def handler_func(client, message, future: asyncio.Future):
            try:
                future.set_result(message)
            except asyncio.InvalidStateError:
                pass

        future = asyncio.Future()
        f = filter_message(message.id)
        if filter:
            f = f & filter
        handler = EditedMessageHandler(async_partial(handler_func, future=future), f)
        await self.add_handler(handler, group=0)
        try:
            yield future
        finally:
            await self.remove_handler(handler, group=0)

    async def wait_reply(
        self,
        chat_id: Union[int, str],
        send: str = None,
        timeout: float = 10,
        outgoing=False,
        filter=None,
    ):
        async with self.catch_reply(chat_id=chat_id, filter=filter) as f:
            if send:
                await self.send_message(chat_id, send)
            msg: types.Message = await asyncio.wait_for(f, timeout)
            return msg

    async def wait_edit(
        self,
        message: types.Message,
        click: Union[str, int] = None,
        timeout: float = 10,
        noanswer=True,
        filter=None,
    ):
        async with self.catch_edit(message, filter=filter) as f:
            if click:
                try:
                    await message.click(click)
                except (TimeoutError, MessageIdInvalid):
                    if noanswer:
                        pass
                    else:
                        raise
            msg: types.Message = await asyncio.wait_for(f, timeout)
            return msg

    async def mute_chat(self, chat_id: Union[int, str], until: Union[int, datetime, None] = None):
        if until is None:
            until = 0x7FFFFFFF  # permanent mute
        elif isinstance(until, datetime):
            until = until.timestamp()
        return await self.invoke(
            raw.functions.account.UpdateNotifySettings(
                peer=raw.types.InputNotifyPeer(peer=await self.resolve_peer(chat_id)),
                settings=raw.types.InputPeerNotifySettings(
                    show_previews=False,
                    mute_until=int(until),
                ),
            )
        )

    async def handle_updates(self, updates):
        if isinstance(updates, (raw.types.Updates, raw.types.UpdatesCombined)):
            is_min = any(
                (
                    await self.fetch_peers(updates.users),
                    await self.fetch_peers(updates.chats),
                )
            )

            users = {u.id: u for u in updates.users}
            chats = {c.id: c for c in updates.chats}

            for update in updates.updates:
                channel_id = getattr(
                    getattr(getattr(update, "message", None), "peer_id", None), "channel_id", None
                ) or getattr(update, "channel_id", None)

                pts = getattr(update, "pts", None)
                pts_count = getattr(update, "pts_count", None)

                if pts and not self.skip_updates:
                    await self.storage.update_state(
                        (
                            utils.get_channel_id(channel_id) if channel_id else 0,
                            pts,
                            None,
                            updates.date,
                            updates.seq,
                        )
                    )

                if isinstance(update, raw.types.UpdateNewChannelMessage) and is_min:
                    message = update.message

                    if not isinstance(message, raw.types.MessageEmpty):
                        try:
                            diff = await self.invoke(
                                raw.functions.updates.GetChannelDifference(
                                    channel=await self.resolve_peer(utils.get_channel_id(channel_id)),
                                    filter=raw.types.ChannelMessagesFilter(
                                        ranges=[
                                            raw.types.MessageRange(
                                                min_id=update.message.id, max_id=update.message.id
                                            )
                                        ]
                                    ),
                                    pts=pts - pts_count,
                                    limit=pts,
                                    force=False,
                                )
                            )
                        except (ChannelPrivate, PersistentTimestampOutdated, PersistentTimestampInvalid):
                            pass
                        else:
                            if not isinstance(diff, raw.types.updates.ChannelDifferenceEmpty):
                                users.update({u.id: u for u in diff.users})
                                chats.update({c.id: c for c in diff.chats})

                self.dispatcher.updates_queue.put_nowait((update, users, chats))

        elif isinstance(updates, (raw.types.UpdateShortMessage, raw.types.UpdateShortChatMessage)):
            if not self.skip_updates:
                await self.storage.update_state((0, updates.pts, None, updates.date, None))

            diff = await self.invoke(
                raw.functions.updates.GetDifference(
                    pts=updates.pts - updates.pts_count, date=updates.date, qts=-1
                )
            )

            if diff.new_messages:
                self.dispatcher.updates_queue.put_nowait(
                    (
                        raw.types.UpdateNewMessage(
                            message=diff.new_messages[0],
                            pts=updates.pts,
                            pts_count=updates.pts_count,
                        ),
                        {u.id: u for u in diff.users},
                        {c.id: c for c in diff.chats},
                    )
                )
            else:
                if diff.other_updates:  # The other_updates list can be empty
                    self.dispatcher.updates_queue.put_nowait((diff.other_updates[0], {}, {}))
        elif isinstance(updates, raw.types.UpdateShort):
            self.dispatcher.updates_queue.put_nowait((updates.update, {}, {}))
