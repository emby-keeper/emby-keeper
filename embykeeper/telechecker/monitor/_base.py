from __future__ import annotations

import asyncio
import random
import re
from contextlib import asynccontextmanager
import string
from typing import Awaitable, Callable, Iterable, List, Optional, Sized, Union

from loguru import logger
from appdirs import user_data_dir
from pyrogram import filters
from pyrogram.enums import ChatType
from pyrogram.errors import UsernameNotOccupied, UserNotParticipant, FloodWait, ChannelInvalid, ChannelPrivate
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from pyrogram.types import Message, User

from embykeeper import __name__ as __product__
from embykeeper.utils import show_exception, to_iterable, truncate_str, AsyncCountPool, optional

from ..tele import Client
from ..link import Link

__ignore__ = True


class Session:
    """回复检测会话, 用于检测跟随回复."""

    def __init__(self, reply, follows=None, delays=None):
        self.reply = reply
        self.follows = follows
        self.delays = delays
        self.lock = asyncio.Lock()
        self.delayed = asyncio.Event()
        self.followed = asyncio.Event()
        self.canceled = asyncio.Event()
        if not self.follows:
            return self.followed.set()

    async def delay(self):
        if not self.delayed:
            return self.delayed.set()
        if isinstance(self.delays, Sized) and len(self.delays) == 2:
            time = random.uniform(*self.delays)
        else:
            time = self.delays
        await asyncio.sleep(time)
        self.delayed.set()

    async def follow(self):
        async with self.lock:
            self.follows -= 1
            if self.follows <= 0:
                self.followed.set()
            return self.follows

    async def wait(self, timeout=240):
        task = asyncio.create_task(self.delay())
        try:
            await asyncio.wait_for(asyncio.gather(self.delayed.wait(), self.followed.wait()), timeout=timeout)
        except asyncio.TimeoutError:
            return False
        else:
            return not self.canceled.is_set()

    async def cancel(self):
        self.canceled.set()
        self.delayed.set()
        self.followed.set()


class UniqueUsername(dict):
    """独特名称类, 用于抢注."""

    def __getitem__(self, user: User):
        if not user.id in self:
            self[user.id] = self.get_unique(user)
        return dict.__getitem__(self, user.id)

    @staticmethod
    def get_unique(user: User):
        """获得一个独特名称, 该名称将在程序运行全周期一致."""
        log = logger.bind(scheme="telemonitor", username=user.name)
        if user.username:
            unique = user.username
        else:
            unique: str = user.name.lower()
        unique = re.sub(r"[^A-Za-z0-9]", "", unique)
        random_bits = 10 - len(unique)
        if random_bits:
            random_bits = "".join(random.choice(string.digits) for _ in range(random_bits))
            unique = unique + random_bits
        log.info(
            f'([magenta]默认[/]) 当监控到开注时, 将以用户名 "{unique}" 注册, 请[yellow]保证[/]具有一定独特性以避免注册失败.'
        )
        return unique


class Monitor:
    """监控器类, 可以检测某个人在某个群中发送了某种模式的信息, 并触发特定的动作 (回复/向机器人注册) 等, 用于答题/抢注等."""

    group_pool = AsyncCountPool(base=1000)
    unique_cache = UniqueUsername()

    name: str = None  # 监控器名称
    chat_name: Union[str, int] = None  # 监控的群聊名称
    chat_allow_outgoing: bool = False  # 是否支持自己发言触发
    chat_user: Union[str, List[str]] = []  # 仅被列表中用户的发言触发 (支持 username / userid)
    chat_keyword: Union[str, List[str]] = []  # 仅当消息含有列表中的关键词时触发, 支持 regex
    chat_except_keyword: Union[str, List[str]] = []  # 消息含有列表中的关键词时不触发, 支持 regex
    chat_probability: float = 1.0  # 发信概率 (0最低, 1最高)
    chat_delay: int = 0  # 发信延迟 (s)
    chat_follow_user: int = 0  # 需要等待 N 个用户发送 {chat_reply} 方可回复
    chat_reply: Union[
        str, Callable[[Message, Optional[Union[str, List[str]]]], Union[str, Awaitable[str]]]
    ] = None  # 回复的内容, 可以为恒定字符串或函数或异步函数
    notify_create_name: bool = False  # 启动时生成 unique name 并提示, 用于抢注
    allow_edit: bool = False  # 编辑消息内容后也触发
    trigger_interval: float = 2  # 每次触发的最低时间间隔
    trigger_sim: int = 1  # 同时触发的最大并行数
    trigger_max_time: float = 120  # 触发后处理的最长时间
    additional_auth: List[str] = []  # 额外认证要求
    debug_no_log = False  # 调试模式不显示冗余日志
    allow_caption: bool = True  # 是否允许带照片的消息
    allow_text: bool = True  # 是否允许不带照片的消息

    def __init__(self, client: Client, nofail=True, basedir=None, proxy=None, config: dict = {}):
        """
        监控器类.
        参数:
            client: Pyrogram 客户端
            nofail: 启用错误处理外壳, 当错误时报错但不退出
            basedir: 文件存储默认位置
            proxy: 代理配置
            config: 当前监控器的特定配置
        """
        self.client = client
        self.nofail = nofail
        self.basedir = basedir or user_data_dir(__product__)
        self.proxy = proxy
        self.config = config
        self.log = logger.bind(scheme="telemonitor", name=self.name, username=client.me.name)
        self.session = None
        self.failed = asyncio.Event()
        if self.trigger_sim:
            self.sem = asyncio.Semaphore(self.trigger_sim)
        else:
            self.sem = None

    def get_filter(self):
        """设定要监控的目标."""
        filter = filters.all
        if self.chat_name:
            filter = filter & filters.chat(self.chat_name)
        if not self.chat_allow_outgoing:
            filter = filter & (~filters.outgoing)
        return filter

    def get_handlers(self):
        """设定要监控的更新的类型."""
        handlers = [MessageHandler(self._message_handler, self.get_filter())]
        if self.allow_edit:
            handlers.append(EditedMessageHandler(self._message_handler, self.get_filter()))
        return handlers

    @asynccontextmanager
    async def listener(self):
        """执行监控上下文."""
        group = await self.group_pool.append(self)
        handlers = self.get_handlers()
        for h in handlers:
            await self.client.add_handler(h, group=group)
        yield
        for h in handlers:
            try:
                await self.client.remove_handler(h, group=group)
            except ValueError:
                pass

    async def _start(self):
        """监控器的入口函数的错误处理外壳."""
        try:
            return await self.start()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if self.nofail:
                self.log.warning(f"发生初始化错误, 监控停止.")
                show_exception(e, regular=False)
                return False
            else:
                raise

    async def start(self):
        """监控器的入口函数."""
        try:
            chat = await self.client.get_chat(self.chat_name)
        except UsernameNotOccupied:
            self.log.warning(f'初始化错误: 群组 "{self.chat_name}" 不存在.')
            return False
        except UserNotParticipant:
            self.log.info(f'跳过监控: 尚未加入群组 "{chat.title}".')
            return False
        except KeyError as e:
            self.log.info(f"初始化错误: 无法访问, 您可能已被封禁.")
            show_exception(e)
            return False
        except (ChannelInvalid, ChannelPrivate) as e:
            self.log.info(f"跳过监控: 私有群组, 未加入, 已跳过.")
            return False
        except FloodWait as e:
            self.log.info(f"初始化信息: Telegram 要求等待 {e.value} 秒.")
            if e.value < 360:
                await asyncio.sleep(e.value)
            else:
                self.log.info(
                    f"初始化信息: Telegram 要求等待 {e.value} 秒, 您可能操作过于频繁, 监控器将停止."
                )
                return False
        try:
            if chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
                await chat.get_member("me")
        except UserNotParticipant:
            self.log.info(f'跳过监控: 尚未加入群组 "{chat.title}".')
            return False
        if self.additional_auth:
            for a in self.additional_auth:
                if not await Link(self.client).auth(a, log_func=self.log.info):
                    return False
        if not await self.init():
            self.log.bind(log=True).warning(f"机器人状态初始化失败, 监控将停止.")
            return False
        if self.notify_create_name:
            self.unique_name = self.get_unique_name()
        if chat.username:
            spec = (
                f"[green]{chat.title}[/] [gray50](@{chat.username})[/]" if chat.title else f"@{chat.username}"
            )
        else:
            spec = f"[green]{chat.title}[/]" if chat.title else f"[green]{chat.id}[/]"
        self.log.info(f"开始监视: {spec}.")
        async with self.listener():
            await self.failed.wait()
            self.log.error(f"发生错误, 不再监视: {spec}.")
            return False

    async def init(self):
        """可重写的初始化函数, 在读取聊天后运行, 在执行监控前运行, 返回 False 将视为初始化错误."""
        return True

    @classmethod
    def keys(cls, message: Message):
        """提取信息中的 keys."""
        sender = message.from_user
        if (
            sender
            and cls.chat_user
            and not any(i in to_iterable(cls.chat_user) for i in (sender.id, sender.username))
        ):
            return
        text = message.text or message.caption
        if cls.chat_except_keyword:
            for k in to_iterable(cls.chat_except_keyword):
                if re.search(k, text, re.IGNORECASE):
                    return
        if cls.chat_keyword:
            for k in to_iterable(cls.chat_keyword):
                if k is None or text is None:
                    if k is None and text is None:
                        yield None
                else:
                    for m in re.findall(k, text, re.IGNORECASE):
                        yield m
        else:
            yield text

    async def get_reply(self, message: Message, key: Union[str, List[str]]):
        """根据 keys 生成回复内容."""
        if callable(self.chat_reply):
            result = self.chat_reply(message, key)
            if asyncio.iscoroutinefunction(self.chat_reply):
                return await result
            else:
                return result
        else:
            return self.chat_reply

    @staticmethod
    def get_spec(keys):
        """返回 keys 的简要表示."""
        if keys is None:
            return "<仅媒体消息>"
        if isinstance(keys, Iterable) and not isinstance(keys, str):
            keys = " ".join([str(k).strip() for k in keys])
        return truncate_str(keys.replace("\n", " ").strip(), 30)

    async def _message_handler(self, client: Client, message: Message):
        """消息处理入口函数的错误处理外壳."""
        try:
            await self.message_handler(client, message)
        except OSError as e:
            self.log.info(f'发生错误: "{e}", 忽略.')
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.failed.set()
            if self.nofail:
                self.log.warning(f"发生错误, 监控器将停止.")
                show_exception(e, regular=False)
            else:
                raise
        finally:
            message.continue_propagation()

    async def message_handler(self, client: Client, message: Message):
        """消息处理入口函数, 控制是否回复以及等待回复."""
        if message.caption and not self.allow_caption:
            return
        if message.text and not self.allow_text:
            return
        for key in self.keys(message):
            spec = self.get_spec(key)
            if not self.debug_no_log:
                if spec:
                    self.log.info(f"监听到关键信息: {truncate_str(spec, 30)}")
                else:
                    self.log.info(f"监听到关键信息.")
            if random.random() >= self.chat_probability:
                self.log.info(f"由于概率设置, 不予回应: {truncate_str(spec, 30)}")
                return False
            reply = await self.get_reply(message, key)
            if self.session:
                await self.session.cancel()
            if self.chat_follow_user:
                self.log.info(f"将等待{self.chat_follow_user}个人回复: {reply}")
            self.session = Session(reply, follows=self.chat_follow_user, delays=self.chat_delay)
            if await self.session.wait():
                self.session = None
                async with optional(self.sem):
                    try:
                        await asyncio.wait_for(self.on_trigger(message, key, reply), self.trigger_max_time)
                    except asyncio.TimeoutError:
                        self.log.warning(f"处理超时: {truncate_str(spec, 30)}")
                    await asyncio.sleep(self.trigger_interval)
        else:
            if self.session and not self.session.followed.is_set():
                text = message.text or message.caption
                if self.session.reply == text:
                    now = await self.session.follow()
                    self.log.info(
                        f'从众计数 ({self.chat_follow_user - now}/{self.chat_follow_user}): "{message.from_user.name}"'
                    )

    async def on_trigger(self, message: Message, key: Optional[Union[List[str], str]], reply: str):
        """
        可修改的回调函数.
        参数:
            message: 引发回复的消息
            key:
                当 chat_keyword 没有 capturing groups 时, 类型为 str, 内容为 regex 的 match
                当 chat_keyword 仅有一个 capturing groups 时, 类型为 str, 内容为 regex 的唯一一个 capturing groups 的对应值
                当 chat_keyword 有多个 capturing groups 时, 类型为 list(str), 内容为 regex 的各个 capturing groups 的对应值
        """
        if reply:
            return await self.client.send_message(message.chat.id, reply)

    def get_unique_name(self):
        """获取唯一性用户名, 用于注册."""
        unique_name = self.config.get("unique_name", None)
        if unique_name:
            self.log.info(f'根据您的设置, 当监控到开注时, 该站点将以用户名 "{unique_name}" 注册.')
            if not re.search("^\w+$", unique_name):
                self.log.warning(f"用户名含有除 a-z, A-Z, 0-9, 以及下划线之外的字符, 可能导致注册失败.")
            return unique_name
        else:
            return Monitor.unique_cache[self.client.me]
