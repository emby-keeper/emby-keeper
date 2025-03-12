import asyncio
import base64
import binascii
import pickle
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

import httpx
from loguru import logger
from pyrogram.errors import ApiIdPublishedFlood, AuthKeyDuplicated, BadMsgNotification, RPCError, Unauthorized
from pyrogram.storage.storage import Storage
from rich.prompt import Prompt

from embykeeper import __name__ as __product__, __version__, var
from embykeeper.utils import get_proxy_str, show_exception, to_iterable
from embykeeper.schema import TelegramAccount
from embykeeper.config import config
from embykeeper.cache import cache

from .pyrogram import Client, logger
from .telethon import TelethonUtils

_id = b"\x80\x04\x95\x15\x00\x00\x00\x00\x00\x00\x00]\x94(K2K3K7K8K5K8K4K6e."
_hash = b"\x80\x04\x95E\x00\x00\x00\x00\x00\x00\x00]\x94(KbKdK7K4K0KeKaK2KaKcKeKeK7K3K9K0KeK0KbK3K5K4KeKcK8K0K9KcK8K7K0Kfe."
_decode = lambda x: "".join(map(chr, to_iterable(pickle.loads(x))))

# "nicegram": {"api_id": "94575", "api_hash": "a3406de8d171bb422bb6ddf3bbd800e2"}
# "tgx-android": {"api_id": "21724", "api_hash": "3e0cb5efcd52300aec5994fdfc5bdc16"}
# "tg-react": {"api_id": "414121", "api_hash": "db09ccfc2a65e1b14a937be15bdb5d4b"}

API_ID = _decode(_id)
API_HASH = _decode(_hash)


class ClientsSession:
    pool = {}
    lock = asyncio.Lock()
    watch = None

    @classmethod
    async def watchdog(cls, timeout=120):
        logger.debug("Telegram 账号池看门狗启动.")
        counter = {}
        while True:
            await asyncio.sleep(10)
            for p in list(cls.pool):
                try:
                    if cls.pool[p][1] <= 0:
                        if p in counter:
                            counter[p] += 1
                            if counter[p] >= timeout / 10:
                                counter[p] = 0
                                await cls.clean(p)
                        else:
                            counter[p] = 1
                    else:
                        counter.pop(p, None)
                except (TypeError, KeyError):
                    pass

    @classmethod
    async def clean(cls, phone: str, force: bool = False):
        async with cls.lock:
            entry = cls.pool.get(phone, None)
            if not entry:
                return
            try:
                client: Client
                client, ref = entry
            except TypeError:
                return
            if force or (not ref):
                logger.debug(f'正在停止账号 "{client.phone_number}" 上的监听和任务.')
                cls.pool.pop(phone, None)
                if client.stop_handlers:
                    logger.debug("开始执行账号的停止处理程序.")
                    try:
                        await asyncio.wait_for(
                            asyncio.gather(*[h() for h in client.stop_handlers], return_exceptions=True),
                            timeout=3,
                        )
                    except asyncio.TimeoutError:
                        logger.warning("部分账号的退出处理程序超时未完成.")
                    else:
                        logger.debug("账号的退出处理程序执行完成, 开始清理监听.")
                else:
                    logger.debug("未注册退出处理程序, 开始清理监听.")
                await client.dispatcher.stop()
                await client.stop()
                logger.debug(f'已停止账号 "{client.phone_number}" 的监听和任务.')

    @classmethod
    async def clean_all(cls, force: bool = False):
        for phone in list(cls.pool):
            await cls.clean(phone, force=force)

    @classmethod
    async def shutdown(cls):
        logger.info(f"正在停止所有 Telegram 账号上的的监听和任务.")
        await cls.clean_all(force=True)

    def __init__(self, accounts: List[TelegramAccount], in_memory=True, proxy=None, basedir=None):
        self.accounts = accounts
        self.phones = []
        self.done = asyncio.Queue()
        self.in_memory = in_memory

        self._proxy = proxy
        self._basedir = basedir

        if not self.watch:
            self.__class__.watch = asyncio.create_task(self.watchdog())
            var.exit_handlers.append(self.__class__.shutdown)

    @property
    def basedir(self):
        return Path(self._basedir) if self._basedir else config.basedir

    @property
    def proxy(self):
        return self._proxy or config.proxy

    async def test_network(self):
        url = "https://telegram.org"
        proxy_str = get_proxy_str(self.proxy)
        try:
            async with httpx.AsyncClient(http2=True, proxy=proxy_str, timeout=20) as client:
                resp = await client.head(url)
                if resp.status_code == 200:
                    return True
                else:
                    logger.warning(f"检测网络状态时发生错误, 网络检测将被跳过.")
                    return False
        except httpx.ProxyError as e:
            if proxy_str:
                logger.warning(
                    f"无法连接到您的代理 ({proxy_str}), 您的网络状态可能不好, 敬请注意. 程序将继续运行."
                )
            return False
        except (httpx.ConnectError, httpx.ConnectTimeout):
            logger.warning(f"无法连接到 Telegram 服务器, 您的网络状态可能不好, 敬请注意. 程序将继续运行.")
            return False
        except Exception as e:
            logger.warning(f"检测网络状态时发生错误, 网络检测将被跳过.")
            show_exception(e)
            return False

    async def test_time(self):
        url = "https://ip.ddnspod.com/timestamp"
        proxy_str = get_proxy_str(self.proxy)
        try:
            async with httpx.AsyncClient(http2=True, proxy=proxy_str) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    timestamp = int(resp.content.decode())
                else:
                    logger.warning(f"世界时间接口异常, 系统时间检测将跳过, 敬请注意. 程序将继续运行.")
                    return False
                nowtime = datetime.now(timezone.utc).timestamp()
                if abs(nowtime - timestamp / 1000) > 30:
                    logger.warning(
                        f"您的系统时间设置不正确, 与世界时间差距过大, 可能会导致连接失败, 敬请注意. 程序将继续运行."
                    )
        except httpx.HTTPError:
            logger.warning(f"检测世界时间发生错误, 时间检测将被跳过.")
            return False
        except Exception as e:
            logger.warning(f"检测世界时间发生错误, 时间检测将被跳过.")
            show_exception(e)
            return False

    async def get_session_str_from_telethon(self, account: TelegramAccount):
        from telethon import TelegramClient
        from telethon.sessions import StringSession

        telethon_proxy = None
        if self.proxy:
            telethon_proxy = {
                "proxy_type": self.proxy.scheme,
                "addr": self.proxy.hostname,
                "port": self.proxy.port,
            }
            if self.proxy.username:
                telethon_proxy["username"] = self.proxy.username
            if self.proxy.password:
                telethon_proxy["password"] = self.proxy.password

        with tempfile.NamedTemporaryFile() as tmp_file:
            client = TelegramClient(
                tmp_file.name,
                api_id=account.api_id or API_ID,
                api_hash=account.api_hash or API_HASH,
                system_version="4.16.30-vxEMBY",
                device_model="A320MH",
                app_version=__version__,
                proxy=telethon_proxy,
            )

            msg1 = f'请输入 "{account.phone}" 的两步验证密码 (不显示, 按回车确认)'
            password_callback = lambda: Prompt.ask(" " * 23 + msg1, password=True, console=var.console)
            msg2 = f'请输入 "{account.phone}" 的登陆验证码 (按回车确认)'
            code_callback = lambda: Prompt.ask(" " * 23 + msg2, console=var.console)

            for _ in range(3):
                try:
                    await TelethonUtils(client).start(
                        phone=account.phone,
                        password=password_callback,
                        code_callback=code_callback,
                    )
                    session_string = StringSession.save(client.session)
                    me = await client.get_me()
                    user_id = me.id
                    user_bot = me.bot
                except asyncio.IncompleteReadError:
                    logger.warning(f'登录账号 "{account.phone}" 时发生网络错误, 将在 3 秒后重试.')
                    await asyncio.sleep(1)
                else:
                    break
                finally:
                    await client.disconnect()
            else:
                return None

        session = StringSession(session_string)
        Dt = Storage.SESSION_STRING_FORMAT
        return (
            base64.urlsafe_b64encode(
                struct.pack(
                    Dt,
                    session.dc_id,
                    int(account.api_id or API_ID),
                    None,
                    session.auth_key.key,
                    user_id,
                    user_bot,
                )
            )
            .decode()
            .rstrip("=")
        )

    async def login(self, account: TelegramAccount, use_telethon=True):
        try:
            self.basedir.mkdir(parents=True, exist_ok=True)
            logger.info(f'登录至账号 "{account.phone}", 请耐心等待.')
            for _ in range(3):
                session_str_src = None
                session_str = account.session
                if session_str:
                    session_str_src = "session"
                else:
                    session_str_key = f"telegram.session_str.{account.get_config_key()}"
                    session_str = cache.get(session_str_key)
                old_login_file = config.basedir / f"{account.phone}.login"
                if not session_str and old_login_file.exists():
                    try:
                        session_str = old_login_file.read_text().strip()
                        cache.set(session_str_key, session_str)
                        old_login_file.unlink()  # Delete old file after migration
                        session_str_src = "cache"
                        logger.info(f'从旧登录文件迁移账号 "{account.phone}" 的登录凭据至缓存.')
                    except Exception as e:
                        logger.warning(f"读取旧版本登录文件时发生错误, 请重新登陆.")
                if session_str:
                    session_str_src = "cache"
                if session_str:
                    logger.debug(
                        f'账号 "{account.phone}" 登录凭据存在, 仅内存模式{"启用" if self.in_memory else "禁用"}.'
                    )
                else:
                    logger.debug(
                        f'账号 "{account.phone}" 登录凭据不存在, 即将进入登录流程, 仅内存模式{"启用" if self.in_memory else "禁用"}.'
                    )
                    if use_telethon:
                        logger.debug("选择使用 Telethon 进行首次登陆, 并导出会话数据至 Pyrogram.")
                        try:
                            session_str = await self.get_session_str_from_telethon(account)
                        except EOFError:
                            logger.warning(
                                "非可交互终端, 无法输入验证码, 如果您使用 docker 请使用 docker -it 运行, 否则请使用可交互终端."
                            )
                            logger.error(f'登录账号 "{account.phone}" 时发生异常, 将被跳过.')
                            return None
                        if session_str:
                            logger.info("请耐心等待, 正在登陆.")
                            await asyncio.sleep(5)
                        else:
                            logger.warning(f'登录账号 "{account.phone}" 尝试次数超限, 将被跳过.')
                            return None
                try:
                    client = Client(
                        app_version=__version__,
                        device_model="A320MH",
                        name=account.phone,
                        system_version="4.16.30-vxEmby",
                        api_id=account.api_id or API_ID,
                        api_hash=account.api_hash or API_HASH,
                        phone_number=account.phone,
                        session_string=session_str,
                        in_memory=self.in_memory,
                        proxy=self.proxy.model_dump() if self.proxy else None,
                        workdir=str(self.basedir),
                        sleep_threshold=30,
                        workers=16,
                    )
                    try:
                        await asyncio.wait_for(client.start(), 20)
                    except asyncio.TimeoutError:
                        if self.proxy:
                            logger.error(f"无法连接到 Telegram 服务器, 请检查您代理的可用性.")
                            continue
                        else:
                            logger.error(f"无法连接到 Telegram 服务器, 请检查您的网络.")
                            continue
                    else:
                        session_str = await client.export_session_string()
                        session_str_key = f"telegram.session_str.{account.get_config_key()}"
                        cache.set(session_str_key, session_str)
                        logger.debug(f'登录账号 "{client.phone_number}" 成功.')
                        return client
                except ApiIdPublishedFlood:
                    logger.warning(f'登录账号 "{account.phone}" 时发生 API key 限制, 将被跳过.')
                    break
                except (Unauthorized, AuthKeyDuplicated) as e:
                    await client.storage.delete()
                    if session_str_src == "session":
                        logger.error(f'账号 "{account.phone}" 由于配置中提供的 session 已被注销, 将被跳过.')
                        show_exception(e)
                        return None
                    elif session_str_src == "cache":
                        logger.error(f'账号 "{account.phone}" 已被注销, 将在 3 秒后重新登录.')
                        show_exception(e)
                        cache.delete(session_str_key)
                        continue
                    else:
                        logger.error(f'账号 "{account.phone}" 已被注销, 将在 3 秒后重新登录.')
                        show_exception(e)
                    await asyncio.sleep(3)
                except KeyError as e:
                    logger.warning(
                        f'登录账号 "{account.phone}" 时发生异常, 可能是由于网络错误, 将在 3 秒后重试.'
                    )
                    show_exception(e)
                    await asyncio.sleep(3)
            else:
                logger.error(f'登录账号 "{account.phone}" 失败次数超限, 将被跳过.')
                return None
        except binascii.Error:
            logger.error(f'登录账号 "{account.phone}" 失败, 由于您在配置文件中提供的 session 无效, 将被跳过.')
        except RPCError as e:
            logger.error(f'登录账号 "{account.phone}" 失败 ({e.MESSAGE.format(value=e.value)}), 将被跳过.')
            return None
        except BadMsgNotification as e:
            if "synchronized" in str(e):
                logger.error(
                    f'登录账号 "{account.phone}" 时发生异常, 可能是因为您的系统时间与世界时间差距过大, 将被跳过.'
                )
                return None
            else:
                logger.error(f'登录账号 "{account.phone}" 时发生异常, 将被跳过.')
                show_exception(e, regular=False)
                return None
        except Exception as e:
            logger.error(f'登录账号 "{account.phone}" 时发生异常, 将被跳过.')
            show_exception(e, regular=False)
            return None

    async def loginer(self, account: TelegramAccount):
        client = await self.login(account)
        async with self.lock:
            if isinstance(client, Client) and client.me:
                self.pool[account.phone] = (client, 1)
                self.phones.append(account.phone)
                await self.done.put((account, client))
                logger.debug(f"Telegram 账号池计数增加: {account.phone} => 1")
            else:
                self.pool[account.phone] = None
                await self.done.put((account, None))

    async def __aenter__(self):
        await self.test_network()
        asyncio.create_task(self.test_time())
        for a in self.accounts:
            try:
                await self.lock.acquire()
                if a.phone not in self.pool:
                    self.pool[a.phone] = asyncio.create_task(self.loginer(a))
                else:
                    if not self.pool[a.phone]:
                        await self.done.put((a, None))
                        continue
                    if isinstance(self.pool[a.phone], asyncio.Task):
                        self.lock.release()
                        await self.pool[a.phone]
                        await self.lock.acquire()
                    client, ref = self.pool[a.phone]
                    ref += 1
                    self.pool[a.phone] = (client, ref)
                    self.phones.append(a.phone)
                    await self.done.put((a, client))
                    logger.debug(f"Telegram 账号池计数增加: {a.phone} => {ref}")
            finally:
                try:
                    self.lock.release()
                except RuntimeError:
                    pass
        return self

    async def __aiter__(self):
        for _ in range(len(self.accounts)):
            account: TelegramAccount
            client: Client
            account, client = await self.done.get()
            if client:
                yield account, client

    async def __aexit__(self, type, value, tb):
        async with self.lock:
            for phone in self.phones:
                entry = self.pool.get(phone, None)
                if entry:
                    client, ref = entry
                    ref -= 1
                    self.pool[phone] = (client, ref)
                    logger.debug(f"Telegram 账号池计数降低: {phone} => {ref}")
