import asyncio
from typing import AsyncGenerator, Optional, Union

from rich.prompt import Prompt
from appdirs import user_data_dir
from loguru import logger
from pyrogram import Client as _Client
from pyrogram import raw, types, utils
from pyrogram.enums import SentCodeType
from pyrogram.errors import BadRequest, RPCError, Unauthorized, SessionPasswordNeeded
from aiocache import Cache

from .. import __name__, __version__
from ..utils import to_iterable

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


class Client(_Client):
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.cache = Cache()

    async def authorize(self):
        if self.bot_token:
            return await self.sign_in_bot(self.bot_token)
        retry = False
        while True:
            try:
                sent_code = await self.send_code(self.phone_number)
                code_target = {
                    SentCodeType.APP: "Telegram客户端",
                    SentCodeType.SMS: "短信",
                    SentCodeType.CALL: "来电",
                    SentCodeType.FLASH_CALL: "闪存呼叫",
                    SentCodeType.FRAGMENT_SMS: "Fragment短信",
                    SentCodeType.EMAIL_CODE: "邮件",
                }
                if not self.phone_code:
                    if retry:
                        msg = f'验证码错误, 请在重新输入 "{self.phone_number}" 的登录验证码: '
                    else:
                        msg = f'请在{code_target[sent_code.type]}接收 "{self.phone_number}" 的登录验证码: '
                    self.phone_code = Prompt.ask(" " * 29 + msg)
                signed_in = await self.sign_in(self.phone_number, sent_code.phone_code_hash, self.phone_code)
            except BadRequest:
                self.phone_code = None
                retry = True
            except SessionPasswordNeeded:
                retry = False
                while True:
                    if not self.password:
                        if retry:
                            msg = f'密码错误, 请重新输入 "{self.phone_number}" 的两步验证密码 (不显示, 按回车确认):'
                        else:
                            msg = f'需要输入 "{self.phone_number}" 的两步验证密码 (不显示, 按回车确认): '
                        self.password = Prompt.ask(" " * 29 + msg, password=True)
                    try:
                        return await self.check_password(self.password)
                    except BadRequest:
                        self.password = None
                        retry = True
            else:
                break
        if isinstance(signed_in, types.User):
            return signed_in
        else:
            raise BadRequest("该账户尚未注册")

    async def get_dialogs(
        self, limit: int = 0, exclude_pinned=None, folder_id=None
    ) -> Optional[AsyncGenerator["types.Dialog", None]]:
        cache_id = f"dialogs_{self.phone_number}_{folder_id}_{1 if exclude_pinned else 0}"
        (offset_id, offset_date, offset_peer), cache = await self.cache.get(
            cache_id, ((0, 0, raw.types.InputPeerEmpty()), [])
        )

        current = 0
        total = limit or (1 << 31) - 1
        limit = min(100, total)

        for c in cache:
            yield c
            current += 1
            if current >= total:
                return

        while True:
            r = await self.invoke(
                raw.functions.messages.GetDialogs(
                    offset_date=offset_date,
                    offset_id=offset_id,
                    offset_peer=offset_peer,
                    limit=limit,
                    hash=0,
                    exclude_pinned=exclude_pinned,
                    folder_id=folder_id,
                ),
                sleep_threshold=60,
            )

            users = {i.id: i for i in r.users}
            chats = {i.id: i for i in r.chats}

            messages = {}

            for message in r.messages:
                if isinstance(message, raw.types.MessageEmpty):
                    continue

                chat_id = utils.get_peer_id(message.peer_id)
                messages[chat_id] = await types.Message._parse(self, message, users, chats)

            dialogs = []

            for dialog in r.dialogs:
                if not isinstance(dialog, raw.types.Dialog):
                    continue

                dialogs.append(types.Dialog._parse(self, dialog, messages, users, chats))

            if not dialogs:
                return

            last = dialogs[-1]

            offset_id = last.top_message.id
            offset_date = utils.datetime_to_timestamp(last.top_message.date)
            offset_peer = await self.resolve_peer(last.chat.id)

            _, cache = await self.cache.get(cache_id, ((0, 0, raw.types.InputPeerEmpty()), []))
            await self.cache.set(cache_id, ((offset_id, offset_date, offset_peer), cache + dialogs), ttl=120)
            for dialog in dialogs:
                yield dialog

                current += 1

                if current >= total:
                    return


class ClientsSession:
    pool = {}
    lock = asyncio.Lock()
    watch = None

    @classmethod
    def from_config(cls, config, **kw):
        accounts = config.get("telegram", [])
        for k, v in kw.items():
            accounts = [a for a in accounts if a.get(k, None) in to_iterable(v)]
        return cls(accounts=accounts, proxy=config.get("proxy", None))

    @classmethod
    async def watchdog(cls, timeout=120):
        logger.debug("Telegram 账号池 watchdog 启动.")
        try:
            counter = {}
            while True:
                await asyncio.sleep(10)
                for p, v in cls.pool.items():
                    try:
                        if v[1] <= 0:
                            if p in counter:
                                counter[p] += 1
                                if counter[p] >= timeout / 10:
                                    await cls.clean(p)
                            else:
                                counter[p] = 1
                        else:
                            counter.pop(p, None)
                    except TypeError:
                        pass
        except asyncio.CancelledError:
            print("\r正在停止... ", end="")
            await cls.shutdown()

    @classmethod
    async def clean(cls, phone):
        async with cls.lock:
            entry = cls.pool.get(phone, None)
            if not entry:
                return
            try:
                client, ref = entry
            except TypeError:
                return
            if not ref:
                logger.debug(f'登出账号 "{client.phone_number}".')
                await client.stop()
                cls.pool.pop(phone, None)

    @classmethod
    async def shutdown(cls):
        for v in cls.pool.values():
            if isinstance(v, asyncio.Task):
                v.cancel()
            else:
                client, ref = v
                client.dispatcher.updates_queue.put_nowait(None)
                for t in client.dispatcher.handler_worker_tasks:
                    try:
                        await t
                    except asyncio.CancelledError:
                        pass
        while len(asyncio.all_tasks()) > 1:
            await asyncio.sleep(0.1)
        print(f"Telegram 账号池停止.", end="")
        for v in cls.pool.values():
            if isinstance(v, tuple):
                client: Client = v[0]
                await client.storage.save()
                await client.storage.close()
                # print(f'登出账号 "{client.phone_number}".')

    def __init__(self, accounts, proxy=None, quiet=False):
        self.accounts = accounts
        self.proxy = proxy
        self.phones = []
        self.done = asyncio.Queue()
        self.quiet = quiet
        if not self.watch:
            self.__class__.watch = asyncio.create_task(self.watchdog())

    async def login(self, account, proxy):
        try:
            if not self.quiet:
                logger.info(f'登录至账号 "{account["phone"]}".')
            while True:
                try:
                    client = Client(
                        app_version=f"{__name__.capitalize()} {__version__}",
                        name=account["phone"],
                        api_id=account["api_id"],
                        api_hash=account["api_hash"],
                        phone_number=account["phone"],
                        proxy=proxy,
                        lang_code="zh",
                        workdir=user_data_dir(__name__),
                    )
                    await client.start()
                except Unauthorized:
                    await client.storage.delete()
                else:
                    break
        except asyncio.CancelledError:
            raise
        except RPCError as e:
            logger.error(f'登录账号 "{client.phone_number}" 失败 ({e.MESSAGE.format(value=e.value)}), 将被跳过.')
        except Exception as e:
            logger.exception(f'登录账号 "{client.phone_number}" 时发生异常, 将被跳过:')
        else:
            return client

    async def loginer(self, account):
        client = await self.login(account, self.proxy)
        if isinstance(client, Client):
            async with self.lock:
                phone = account["phone"]
                self.pool[phone] = (client, 1)
                self.phones.append(phone)
                await self.done.put(client)

    async def __aenter__(self):
        for a in self.accounts:
            phone = a["phone"]
            async with self.lock:
                if phone in self.pool:
                    if isinstance(self.pool[phone], asyncio.Task):
                        self.lock.release()
                        await self.pool[phone]
                        await self.lock.acquire()
                    client, ref = self.pool[phone]
                    ref += 1
                    self.pool[phone] = (client, ref)
                    await self.done.put(client)
                else:
                    self.pool[phone] = asyncio.create_task(self.loginer(a))
        return self

    def __aiter__(self):
        async def aiter():
            for _ in range(len(self.accounts)):
                client: Client = await self.done.get()
                if client == None:
                    break
                yield client

        return aiter()

    async def __aexit__(self, type, value, tb):
        async with self.lock:
            for phone in self.phones:
                entry = self.pool.get(phone, None)
                client, ref = entry
                ref -= 1
                self.pool[phone] = (client, ref)
                # print(f"Telegram 账号池计数 {client.phone_number} => {ref}.")
