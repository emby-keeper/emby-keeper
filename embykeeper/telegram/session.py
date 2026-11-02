import asyncio
import base64
import binascii
import pickle
import struct
import tempfile
import glob
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List
import os
import random

import httpx
from pyrogram.errors import ApiIdPublishedFlood, AuthKeyDuplicated, BadMsgNotification, RPCError, Unauthorized
from pyrogram.session.session import AuthKeyNotFound
from pyrogram.storage.storage import Storage
from pyrogram.session import Session
from rich.prompt import Prompt

from embykeeper import __name__ as __product__, __version__, var
from embykeeper.utils import get_proxy_str, show_exception, to_iterable
from embykeeper.schema import TelegramAccount
from embykeeper.config import config
from embykeeper.cache import cache

from .pyrogram import Client, logger
from .telethon import TelethonUtils

_id = b"\x80\x04\x95\x15\x00\x00\x00\x00\x00\x00\x00]\x94(K2K2K9K7K9K6K4K8e."
_hash = b"\x80\x04\x95E\x00\x00\x00\x00\x00\x00\x00]\x94(K7K8KeKeKfKcKfKbK9K8K9KeK1K1K0KcK0KdK3K0K7K8K3K8K5KfK9K9K7KaKeKee."
_test_dc_id = 2
_test_dc_ip = "149.154.167.40"
_test_dc_port = 443
_decode = lambda x: "".join(map(chr, to_iterable(pickle.loads(x))))

# "nicegram": {"api_id": "94575", "api_hash": "a3406de8d171bb422bb6ddf3bbd800e2"}
# "tgx-android": {"api_id": "21724", "api_hash": "3e0cb5efcd52300aec5994fdfc5bdc16"}
# "tg-react": {"api_id": "414121", "api_hash": "db09ccfc2a65e1b14a937be15bdb5d4b"}

API_ID = _decode(_id)
API_HASH = _decode(_hash)


def get_telethon_proxy(proxy):
    if not proxy:
        return None
    telethon_proxy = {
        "proxy_type": proxy.scheme,
        "addr": proxy.hostname,
        "port": proxy.port,
    }
    if proxy.username:
        telethon_proxy["username"] = proxy.username
    if proxy.password:
        telethon_proxy["password"] = proxy.password
    return telethon_proxy


def build_pyrogram_client_params(
    name: str,
    session_string: str,
    api_id: int,
    api_hash: str,
    phone_number: str,
    *,
    in_memory: bool,
    proxy,
    workdir: str,
    app_version: str = __version__,
) -> dict:
    return {
        "app_version": app_version,
        "device_model": "A320MH",
        "name": name,
        "system_version": "4.16.30-vxEmby",
        "api_id": api_id,
        "api_hash": api_hash,
        "phone_number": phone_number,
        "session_string": session_string,
        "in_memory": in_memory,
        "proxy": proxy.model_dump() if proxy else None,
        "workdir": workdir,
        "sleep_threshold": 120,
        "workers": 16,
        "test_mode": var.telegram_test_server,
    }


def is_valid_pyrogram_session_string(session_str: str) -> bool:
    try:
        raw = base64.urlsafe_b64decode(session_str + "=" * (-len(session_str) % 4))
        struct.unpack(Storage.SESSION_STRING_FORMAT, raw)
        return True
    except Exception:
        return False


def convert_telethon_session_string(
    session_str: str, api_id: int, test_mode: bool, user_id: int, is_bot: int
) -> str:
    """Convert a telethon session string to the pyrogram session string format."""
    from telethon.sessions import StringSession

    session = StringSession(session_str)
    return (
        base64.urlsafe_b64encode(
            struct.pack(
                Storage.SESSION_STRING_FORMAT,
                session.dc_id,
                int(api_id),
                int(bool(test_mode)),
                session.auth_key.key,
                user_id,
                int(is_bot),
            )
        )
        .decode()
        .rstrip("=")
    )


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
            # Check if entry is a Task (account still logging in)
            if isinstance(entry, asyncio.Task):
                entry.cancel()
                cls.pool.pop(phone, None)
                return
            try:
                client: Client
                client, ref = entry
            except TypeError:
                return
            if force or (not ref):
                phone_masked = TelegramAccount.get_phone_masked(client.phone_number)
                logger.debug(f'正在停止账号 "{phone_masked}" 上的监听和任务.')
                cls.pool.pop(phone, None)
                if client.stop_handlers:
                    logger.debug(
                        f'开始执行账号 "{phone_masked}" 的停止处理程序, 共 {len(client.stop_handlers)} 个.'
                    )
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
                await client.stop()
                await client.storage.delete()
                logger.debug(f'已停止账号 "{phone_masked}" 的监听和任务.')

    @classmethod
    async def clean_all(cls, force: bool = False):
        for phone in list(cls.pool):
            await cls.clean(phone, force=force)

    @classmethod
    async def shutdown(cls):
        logger.info(f"正在停止所有 Telegram 账号上的的监听和任务.")
        await cls.clean_all(force=True)

    def __init__(self, accounts: List[TelegramAccount], in_memory=False, proxy=None, basedir=None):
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
        return self._proxy or (config.proxy if config.telegram.use_proxy else None)

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
            if self.proxy:
                logger.warning(
                    f"无法连接到 Telegram 服务器, 您的网络状态可能不好, 或代理无法连接, 敬请注意. 程序将继续运行."
                )
            else:
                logger.warning(
                    f"无法连接到 Telegram 服务器, 您的网络状态可能不好, 敬请注意. 您可以通过配置文件设置代理. 程序将继续运行."
                )
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

        with tempfile.NamedTemporaryFile() as tmp_file:
            client = TelegramClient(
                tmp_file.name,
                api_id=account.api_id or API_ID,
                api_hash=account.api_hash or API_HASH,
                system_version="4.16.30-vxEmby",
                device_model="A320MH",
                app_version=__version__,
                proxy=get_telethon_proxy(self.proxy),
            )

            if var.telegram_test_server:
                client.session.set_dc(_test_dc_id, _test_dc_ip, _test_dc_port)

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
                    if client.is_connected():
                        try:
                            await asyncio.wait_for(client.disconnect(), timeout=2.0)
                        except asyncio.TimeoutError:
                            logger.debug("等待 Telethon 客户端断开超时.")
                        except Exception:
                            pass
            else:
                return None

        return convert_telethon_session_string(
            session_string,
            int(account.api_id or API_ID),
            int(bool(var.telegram_test_server)),
            user_id,
            int(user_bot),
        )

    async def _disconnect_handler(self, client: Client, session: Session):
        logger.bind(username=client.me.full_name).debug("客户端与 Telegram 服务器断开连接.")

    async def _connect_handler(self, client: Client, session: Session):
        logger.bind(username=client.me.full_name).debug("已连接到 Telegram 服务器.")

    async def login(self, account: TelegramAccount, use_telethon=True):
        try:
            self.basedir.mkdir(parents=True, exist_ok=True)
            phone_masked = TelegramAccount.get_phone_masked(account.phone)
            logger.info(f'登录至账号 "{phone_masked}", 请耐心等待.')

            if not self.in_memory:
                session_base = str(self.basedir / f"{account.phone}")
                for session_file in glob.glob(f"{session_base}_[0-9]*.session"):
                    try:
                        conn = sqlite3.connect(session_file, timeout=0.1)
                        conn.close()
                        try:
                            os.remove(session_file)
                            logger.debug(f"已清理未被占用的会话文件: {session_file}")
                        except OSError:
                            pass
                    except sqlite3.OperationalError:
                        pass

            for i in range(3):
                session_str_src = None
                session_str = account.session
                is_newly_created_session = False
                if session_str:
                    session_str_src = "session"
                else:
                    session_str_key = f"telegram.session_str.{account.get_config_key()}"
                    session_str = cache.get(session_str_key)
                    if session_str:
                        session_str_src = "cache"
                old_login_file = config.basedir / f"{account.phone}.login"
                if not session_str and old_login_file.exists():
                    try:
                        session_str = old_login_file.read_text().strip()
                        cache.set(session_str_key, session_str)
                        old_login_file.unlink()
                        session_str_src = "cache"
                        logger.info(f'从旧版本登录文件迁移账号 "{phone_masked}" 的登录凭据至缓存.')
                    except Exception as e:
                        logger.warning(f"读取旧版本登录文件时发生错误, 请重新登陆.")
                if session_str:
                    logger.debug(
                        f'账号 "{phone_masked}" 登录凭据存在, 仅内存模式{"启用" if self.in_memory else "禁用"}.'
                    )
                else:
                    is_newly_created_session = True
                    logger.debug(
                        f'账号 "{phone_masked}" 登录凭据不存在, 即将进入登录流程, 仅内存模式{"启用" if self.in_memory else "禁用"}.'
                    )
                    if use_telethon:
                        logger.debug("选择使用 Telethon 进行首次登陆, 并导出会话数据至 Pyrogram.")
                        try:
                            session_str = await self.get_session_str_from_telethon(account)
                        except EOFError:
                            logger.warning(
                                "非可交互终端, 无法输入验证码, 如果您使用 docker 请使用 docker -it 运行, 否则请使用可交互终端."
                            )
                            logger.error(f'登录账号 "{phone_masked}" 时发生异常, 将被跳过.')
                            return None
                        if session_str:
                            logger.info("请耐心等待, 正在登陆.")
                            await asyncio.sleep(5)
                        else:
                            logger.warning(f'登录账号 "{phone_masked}" 尝试次数超限, 将被跳过.')
                            return None

                client_params = build_pyrogram_client_params(
                    account.phone,
                    session_str,
                    account.api_id or API_ID,
                    account.api_hash or API_HASH,
                    account.phone,
                    in_memory=self.in_memory,
                    proxy=self.proxy,
                    workdir=str(self.basedir),
                )

                try:
                    client = Client(**client_params)
                    try:
                        await client.start()
                    except asyncio.TimeoutError:
                        try:
                            await client.stop()
                        except Exception:
                            pass
                        if self.proxy:
                            logger.error(
                                f"无法连接到 Telegram 服务器, 请检查您代理的可用性, 正在重试 ({i+1} / 3)."
                            )
                            await asyncio.sleep(3)
                            continue
                        else:
                            logger.error(f"无法连接到 Telegram 服务器, 请检查您的网络, 正在重试 ({i+1} / 3).")
                            await asyncio.sleep(3)
                            continue
                    else:
                        session_str = await client.export_session_string()
                        session_str_key = f"telegram.session_str.{account.get_config_key()}"
                        cache.set(session_str_key, session_str)
                        client.disconnect_handler = self._disconnect_handler
                        client.connect_handler = self._connect_handler
                        logger.debug(f'登录账号 "{phone_masked}": "{client.me.full_name}" 成功.')
                        return client
                except ApiIdPublishedFlood:
                    logger.warning(f'登录账号 "{phone_masked}" 时发生 API key 限制, 将被跳过.')
                    break
                except (Unauthorized, AuthKeyDuplicated, AuthKeyNotFound) as e:
                    if is_newly_created_session:
                        logger.error(f'账号 "{phone_masked}" 新生成的会话凭据无法被客户端使用, 登录失败.')
                        show_exception(e)
                        return None
                    await client.storage.delete()
                    if session_str_src == "session":
                        logger.error(f'账号 "{phone_masked}" 由于配置中提供的 session 已被注销, 将被跳过.')
                        show_exception(e)
                        return None
                    elif session_str_src == "cache":
                        logger.error(f'账号 "{phone_masked}" 已被注销, 将在 3 秒后重新登录.')
                        show_exception(e)
                        cache.delete(session_str_key)
                        await asyncio.sleep(3)
                        continue
                    else:
                        logger.error(f'账号 "{phone_masked}" 已被注销, 将在 3 秒后重新登录.')
                        show_exception(e)
                    await asyncio.sleep(3)
                except KeyError as e:
                    logger.warning(
                        f'登录账号 "{phone_masked}" 时发生异常, 可能是由于网络错误, 将在 3 秒后重试.'
                    )
                    show_exception(e)
                    await asyncio.sleep(3)
            else:
                logger.error(f'登录账号 "{phone_masked}" 失败次数超限, 将被跳过.')
                return None
        except binascii.Error:
            logger.error(f'登录账号 "{phone_masked}" 失败, 由于您在配置文件中提供的 session 无效, 将被跳过.')
        except RPCError as e:
            logger.error(f'登录账号 "{phone_masked}" 失败 ({e.MESSAGE.format(value=e.value)}), 将被跳过.')
            return None
        except BadMsgNotification as e:
            if "synchronized" in str(e):
                logger.error(
                    f'登录账号 "{phone_masked}" 时发生异常, 可能是因为您的系统时间与世界时间差距过大, 将被跳过.'
                )
                return None
            else:
                logger.error(f'登录账号 "{phone_masked}" 时发生异常, 将被跳过.')
                show_exception(e, regular=False)
                return None
        except Exception as e:
            logger.error(f'登录账号 "{phone_masked}" 时发生异常, 将被跳过.')
            show_exception(e, regular=False)
            return None

    async def loginer(self, account: TelegramAccount):
        client = await self.login(account)
        async with self.lock:
            if isinstance(client, Client) and client.me:
                self.pool[account.phone] = (client, 1)
                self.phones.append(account.phone)
                await self.done.put((account, client))
                phone_masked = TelegramAccount.get_phone_masked(account.phone)
                logger.debug(f'Telegram 账号池计数增加: "{phone_masked}" => 1')
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
                    result = self.pool[a.phone]
                    if not result:
                        await self.done.put((a, None))
                    client, ref = result
                    ref += 1
                    self.pool[a.phone] = (client, ref)
                    self.phones.append(a.phone)
                    await self.done.put((a, client))
                    phone_masked = TelegramAccount.get_phone_masked(a.phone)
                    logger.debug(f'Telegram 账号池计数增加: "{phone_masked}" => {ref}')
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
                    phone_masked = TelegramAccount.get_phone_masked(phone)
                    logger.debug(f'Telegram 账号池计数降低: "{phone_masked}" => {ref}')
