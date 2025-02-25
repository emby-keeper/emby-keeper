import asyncio
from datetime import datetime, timedelta
import random
import re
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from enum import Flag, IntEnum, auto
import string
import time
from typing import Iterable, List, Optional, Union

from appdirs import user_data_dir
from loguru import logger
from pyrogram import filters
from pyrogram.errors import (
    UsernameNotOccupied,
    FloodWait,
    UsernameInvalid,
    ChannelInvalid,
    ChannelPrivate,
    MessageIdInvalid,
)
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from pyrogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from pyrogram.raw.functions.account import GetNotifySettings
from pyrogram.raw.types import PeerNotifySettings, InputNotifyPeer
from thefuzz import fuzz, process

from embykeeper import __name__ as __product__
from embykeeper.ocr import CharRange, OCRService
from embykeeper.utils import show_exception, to_iterable, format_timedelta_human, AsyncCountPool

from ..tele import Client
from ..link import Link

__ignore__ = True

default_keywords = {
    "account_fail": (
        "拉黑",
        "黑名单",
        "冻结",
        "未找到用户",
        "无资格",
        "退出群",
        "退群",
        "加群",
        "加入群聊",
        "请先关注",
        "请先加入",
        "請先加入",
        "未注册",
        "先注册",
        "不存在",
        "不在群组中",
    ),
    "too_many_tries_fail": ("已尝试", "过多"),
    "checked": ("只能", "已经", "下次", "过了", "签过", "明日再来", "上次签到", "重复签到"),
    "fail": ("失败", "错误", "超时"),
    "success": ("成功", "通过", "完成", "获得"),
}


class MessageType(Flag):
    IGNORE = auto()
    TEXT = auto()
    CAPTION = auto()
    CAPTCHA = auto()
    ANSWER = auto()


class CheckinResult(IntEnum):
    SUCCESS = auto()
    CHECKED = auto()
    FAIL = auto()
    IGNORE = auto()


class BaseBotCheckin(ABC):
    """基础签到类."""

    name: str = None

    def __init__(
        self,
        client: Client,
        retries=4,
        timeout=240,
        nofail=True,
        basedir=None,
        proxy=None,
        config: dict = {},
        **kw,
    ):
        """
        基础签到类.
        参数:
            client: Pyrogram 客户端
            retries: 最大重试次数
            timeout: 签到超时时间
            nofail: 启用错误处理外壳, 当错误时报错但不退出
            basedir: 文件存储默认位置
            proxy: 代理配置
            config: 当前签到器的特定配置
        """
        self.client = client
        self.retries = retries
        self.timeout = timeout
        self.nofail = nofail
        self.basedir = basedir or user_data_dir(__product__)
        self.proxy = proxy
        self.config = config
        self.finished = asyncio.Event()  # 签到完成事件
        self.log = logger.bind(scheme="telechecker", name=self.name, username=client.me.name)  # 日志组件

    async def _start(self):
        """签到器的入口函数的错误处理外壳."""
        try:
            return self.name, await self.start()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if self.nofail:
                self.log.warning(f"初始化错误, 签到器将停止.")
                show_exception(e, regular=False)
                return self.name, False
            else:
                raise

    @abstractmethod
    async def start(self):
        pass


class BotCheckin(BaseBotCheckin):
    """签到类, 用于回复模式签到."""

    group_pool = AsyncCountPool(base=2000)
    interval_pool = {}

    # fmt: off
    name: str = None  # 签到器的名称
    bot_username: Union[int, str] = None  # Bot 的 UserID 或 用户名 (不带 @ 或 https://t.me/)
    bot_checkin_cmd: Union[str, List[str]] = ["/checkin"]  # Bot 依次执行的签到命令
    bot_send_interval: int = 3  # 签到命令间等待的秒数
    bot_use_captcha = True # 当 Bot 返回图片时, 识别验证码并调用 on_captcha
    bot_checkin_caption_pat: str = None  # 当 Bot 返回图片时, 仅当符合该 regex 才识别为验证码, 置空不限制
    bot_text_ignore: Union[str, List[str]] = []  # 当含有列表中的关键词, 即忽略该消息, 置空不限制
    ocr: Optional[str] = None # OCR 模型, None = 默认模型, str = 自定义模型
    bot_captcha_char_range: Optional[Union[CharRange, str]] = None # OCR 字符范围, 仅当默认模型可用, None = 默认范围, OCRRanges = 预定义范围, str = 自定义范围
    bot_captcha_len: Union[int, Iterable[int]] = []  # 验证码长度的可能范围, 例如 [1, 2, 3], 置空不限制
    bot_success_pat: str = r"(\d+)[^\d]*(\d+)"  # 当接收到成功消息后, 从消息中提取数字的模式
    bot_retry_wait: int = 2  # 失败时等待的秒数
    bot_use_history: int = None  # 首先尝试识别历史记录中最后一个验证码图片, 最多识别 N 条, 置空禁用
    bot_allow_from_scratch: bool = False  # 允许从未聊天情况下启动
    bot_success_keywords: Union[str, List[str]] = []  # 成功时检测的关键词 (暂不支持regex), 置空使用内置关键词表
    bot_checked_keywords: Union[str, List[str]] = []  # 今日已签到时检测的关键词, 置空使用内置关键词表
    bot_account_fail_keywords: Union[str, List[str]] = []  # 账户错误将退出时检测的关键词 (暂不支持regex), 置空使用内置关键词表
    bot_too_many_tries_fail_keywords: Union[str, List[str]] = []  # 账户错误将退出时检测的关键词 (暂不支持regex), 置空使用内置关键词表
    bot_fail_keywords: Union[str, List[str]] = []  # 签到错误将重试时检测的关键词 (暂不支持regex), 置空使用内置关键词表
    chat_name: str = None  # 在群聊中向机器人签到
    additional_auth: List[str] = []  # 额外认证要求
    max_retries = None  # 验证码错误或网络错误时最高重试次数 (默认无限)
    checked_retries = None # 今日已签到时最高重试次数 (默认不重试)
    skip = None # 跳过签到次数 (默认不跳过)
    # fmt: on

    @property
    def valid_retries(self):
        if self.max_retries:
            return min(self.retries, self.max_retries)
        else:
            return self.retries

    def __init__(self, *args, instant=False, **kw):
        super().__init__(*args, **kw)
        self._checked = False  # 当前结束状态为已签到
        self._retries = 0  # 当前重试次数
        self._checked_retries = 0
        self._waiting = {}  # 当前等待的消息
        if instant:
            self.checked_retries = None

    def get_filter(self):
        """设定要签到的目标."""
        filter = filters.all
        if self.bot_username:
            filter = filter & filters.user(self.bot_username)
        if self.chat_name:
            filter = filter & filters.chat(self.chat_name)
        else:
            filter = filter & filters.private
        return filter

    def get_handlers(self):
        """设定要监控的更新的类型."""
        return [
            MessageHandler(self._message_handler, self.get_filter()),
            EditedMessageHandler(self._message_handler, self.get_filter()),
        ]

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

    async def start(self):
        """签到器的入口函数."""
        skip = self.config.get("skip", None)
        quiet = False
        if not skip:
            if self.skip:
                quiet = True
                skip = self.skip
        if skip:
            current_count = self.interval_pool.get(self.client.me.id, None)
            if current_count is None:
                self.interval_pool[self.client.me.id] = 0
            else:
                if current_count < skip:
                    self.interval_pool[self.client.me.id] += 1
                    if not quiet:
                        self.log.info(f"跳过签到: 根据配置跳过 (还需跳过 {skip - current_count} 次).")
                    return CheckinResult.IGNORE
                else:
                    self.interval_pool[self.client.me.id] = 0
        if (not self.chat_name) and (not self.bot_username):
            raise ValueError("未指定 chat_name 或 bot_username")
        ident = self.chat_name or self.bot_username
        while True:
            try:
                chat = await self.client.get_chat(ident)
            except (UsernameNotOccupied, UsernameInvalid, ChannelInvalid, ChannelPrivate) as e:
                self.log.warning(f'初始化错误: 会话 "{ident}" 已不存在.')
                return CheckinResult.FAIL
            except KeyError as e:
                self.log.info(f"初始化错误: 无法访问, 您可能已被封禁: {e}.")
                show_exception(e)
                return CheckinResult.FAIL
            except FloodWait as e:
                if e.value < 360:
                    self.log.info(f"初始化信息: Telegram 要求等待 {e.value} 秒.")
                    await asyncio.sleep(e.value)
                else:
                    self.log.info(
                        f"初始化信息: Telegram 要求等待 {e.value} 秒, 您可能操作过于频繁, 签到器将停止."
                    )
                    return CheckinResult.FAIL
            else:
                break

        _is_archived = False
        async for d in self.client.get_dialogs(folder_id=1):
            if d.chat.id == chat.id:
                _is_archived = True
                break
        else:
            async for d in self.client.get_dialogs(folder_id=0):
                if d.chat.id == chat.id:
                    break
            else:
                if not self.bot_allow_from_scratch:
                    self.log.debug(f'跳过签到: 从未与 "{ident}" 交流.')
                    return CheckinResult.IGNORE

        while True:
            if self.additional_auth:
                for a in self.additional_auth:
                    if not await Link(self.client).auth(a, log_func=self.log.info):
                        return CheckinResult.IGNORE

            if not await self.init():
                self.log.warning(f"初始化错误.")
                return CheckinResult.FAIL

            specs = []
            if self.bot_username:
                bot = await self.client.get_users(self.bot_username)
                specs.append(f"[green]{bot.name}[/] [gray50](@{bot.username})[/]")
            if chat.title:
                specs.append(f"[green]{chat.title}[/] [gray50](@{chat.username})[/]")
            self.log.info(f"开始执行签到: {' @ '.join(specs)}.")

            if not self.chat_name:
                self.log.debug(f"[gray50]禁用提醒 {self.timeout} 秒: {bot.username}[/]")
                peer = InputNotifyPeer(peer=await self.client.resolve_peer(ident))
                settings: PeerNotifySettings = await self.client.invoke(GetNotifySettings(peer=peer))
                old_mute_until = settings.mute_until
                try:
                    await self.client.mute_chat(ident, time.time() + self.timeout + 10)
                except FloodWait:
                    self.log.debug(f"[gray50]设置禁用提醒因访问超限而失败: {bot.username}[/]")
            try:
                async with self.listener():
                    cancelled = False
                    try:
                        if self.bot_use_history is None:
                            await self.send_checkin()
                        elif not await self.walk_history(self.bot_use_history):
                            await self.send_checkin()
                        await asyncio.wait_for(self.finished.wait(), self.timeout)
                    except asyncio.CancelledError:
                        cancelled = True
                        raise
                    finally:
                        if not cancelled:
                            if not await self.cleanup():
                                self.log.debug(f"[gray50]执行清理失败: {ident}[/]")
                            if _is_archived:
                                self.log.debug(f"[gray50]将会话重新归档: {ident}[/]")
                                try:
                                    if await chat.archive():
                                        self.log.debug(f"[gray50]重新归档成功: {ident}[/]")
                                except asyncio.TimeoutError:
                                    self.log.debug(f"[gray50]归档失败: {ident}[/]")
                            if not self.chat_name:
                                self.log.debug(f"[gray50]将会话设为已读: {ident}[/]")
                                try:
                                    if await self.client.read_chat_history(ident):
                                        self.log.debug(f"[gray50]设为已读成功: {ident}[/]")
                                except asyncio.TimeoutError:
                                    self.log.debug(f"[gray50]设为已读失败: {ident}[/]")
            except OSError as e:
                self.log.warning(f'初始化错误: "{e}", 签到器将停止.')
                show_exception(e)
                return CheckinResult.FAIL
            except asyncio.TimeoutError:
                pass
            finally:
                if not self.chat_name:
                    if old_mute_until:
                        try:
                            await asyncio.wait_for(self.client.mute_chat(ident, until=old_mute_until), 3)
                        except asyncio.TimeoutError:
                            self.log.debug(f"[gray50]重新设置通知设置失败: {ident}[/]")
                        except FloodWait:
                            self.log.debug(f"[gray50]重新设置通知设置因访问超限而失败: {ident}[/]")
                        else:
                            self.log.debug(f"[gray50]重新设置通知设置成功: {ident}[/]")
            if not self.finished.is_set():
                self.log.warning("无法在时限内完成签到.")
                return CheckinResult.FAIL
            elif self._retries <= self.valid_retries:
                if self._checked:
                    if self.checked_retries and self._checked_retries < self.checked_retries:
                        self._checked_retries += 1
                        now = datetime.now()
                        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
                        max_sleep = midnight - now
                        sleep = timedelta(hours=min(self._checked_retries * 3, 6))
                        if sleep > max_sleep:
                            return CheckinResult.CHECKED
                        else:
                            self.log.info(
                                f"今日已签到, 即将在 {format_timedelta_human(sleep)} 后重试, 重试不发送日志."
                            )
                            asyncio.create_task(self._start())
                    return CheckinResult.CHECKED
                else:
                    return CheckinResult.SUCCESS
            else:
                return CheckinResult.FAIL

    async def init(self):
        """可重写的初始化函数, 在读取聊天后运行, 在执行签到前运行, 返回 False 将视为初始化错误."""
        return True

    async def cleanup(self):
        """可重写的签到结束后的清理函数, 执行签到成功或失败后运行, 返回 False 将视为清理错误."""
        return True

    async def walk_history(self, limit=0):
        """处理 limit 条历史消息, 并检测是否有验证码."""
        try:
            async for m in self.client.get_chat_history(self.chat_name or self.bot_username, limit=limit):
                if MessageType.CAPTCHA in self.message_type(m):
                    await self.on_photo(m)
                    return True
            return False
        except Exception as e:
            self.log.warning("读取历史消息失败, 将不再读取历史消息.")
            show_exception(e)
            return False

    async def send(self, cmd):
        """向机器人发送命令."""
        if self.chat_name:
            await self.client.send_message(self.chat_name, cmd)
        else:
            await self.client.send_message(self.bot_username, cmd)

    async def send_checkin(self, retry=False):
        """发送签到命令, 或依次发送签到命令序列."""
        cmds = to_iterable(self.bot_checkin_cmd)
        for i, cmd in enumerate(cmds):
            if retry and not i:
                await asyncio.sleep(self.bot_retry_wait)
            if i < len(cmds):
                await asyncio.sleep(self.bot_send_interval)
            await self.send(cmd)

    async def _message_handler(self, client: Client, message: Message):
        """消息处理入口函数的错误处理外壳."""
        try:
            await self.message_handler(client, message)
        except OSError as e:
            self.log.info(f'发生错误: "{e}", 正在重试.')
            show_exception(e)
            await self.retry()
            message.continue_propagation()
        except asyncio.CancelledError:
            raise
        except Exception as e:
            if not self.nofail:
                await self.fail()
                raise
            else:
                self.log.warning(f"发生错误, 签到器将停止.")
                show_exception(e, regular=False)
                await self.fail()
                message.continue_propagation()
        else:
            message.continue_propagation()

    async def message_handler(self, client: Client, message: Message, type=None):
        """消息处理入口函数."""
        text = message.text or message.caption
        if text:
            for p, k in self._waiting.items():
                if re.search(p, text):
                    k.set()
                    self._waiting[p] = message
        type = type or self.message_type(message)
        if type:
            if MessageType.TEXT in type:
                await self.on_text(message, message.text)
            if MessageType.CAPTION in type:
                await self.on_text(message, message.caption)
            if MessageType.CAPTCHA in type:
                await self.on_photo(message)

    def message_type(self, message: Message):
        """分析传入消息的类型为验证码或文字."""
        if message.photo:
            if message.caption:
                if self.bot_use_captcha:
                    if self.bot_checkin_caption_pat:
                        if re.search(self.bot_checkin_caption_pat, message.caption):
                            return MessageType.CAPTCHA
                        else:
                            return MessageType.CAPTION
                    else:
                        return MessageType.CAPTCHA
                else:
                    return MessageType.CAPTION
            else:
                if self.bot_use_captcha:
                    return MessageType.CAPTCHA
                else:
                    return MessageType.IGNORE
        elif message.text:
            return MessageType.TEXT
        else:
            return MessageType.IGNORE

    async def on_photo(self, message: Message):
        """分析分析传入的验证码图片并返回验证码."""
        data = await self.client.download_media(message, in_memory=True)
        ocr = await OCRService.get(
            ocr_name=self.ocr,
            char_range=self.bot_captcha_char_range,
            basedir=self.basedir,
            proxy=self.proxy,
        )
        try:
            with ocr:
                ocr_text = await ocr.run(data)
        except asyncio.TimeoutError:
            self.log.info("签到失败: 验证码识别失败, 正在重试.")
            await self.retry()
            return
        captcha = ocr_text.translate(str.maketrans("", "", string.punctuation)).replace(" ", "")
        if captcha:
            self.log.debug(f"[gray50]接收验证码: {captcha}.[/]")
            if self.bot_captcha_len and len(captcha) not in to_iterable(self.bot_captcha_len):
                self.log.info(f"签到失败: 验证码低于设定长度, 正在重试.")
                await self.retry()
            else:
                await asyncio.sleep(random.uniform(2, 4))
                await self.on_captcha(message, captcha)
        else:
            self.log.info(f"签到失败: 接收到空验证码, 正在重试.")
            await self.retry()

    async def on_captcha(self, message: Message, captcha: str):
        """
        可修改的回调函数.
            message: 包含验证码图片的消息
            captcha: OCR 识别的验证码
        """
        await message.reply(captcha)

    async def on_text(self, message: Message, text: str):
        """接收非验证码消息时, 检测关键词并确认签到成功或失败, 发送用户提示."""
        if not text:
            return
        if any(s in text for s in to_iterable(self.bot_text_ignore)):
            pass
        elif any(
            s in text for s in to_iterable(self.bot_account_fail_keywords) or default_keywords["account_fail"]
        ):
            self.log.warning(f"签到失败: 账户错误.")
            await self.fail()
        elif any(
            s in text
            for s in to_iterable(self.bot_too_many_tries_fail_keywords)
            or default_keywords["too_many_tries_fail"]
        ):
            self.log.warning(f"签到失败: 尝试次数过多.")
            await self.fail()
        elif any(s in text for s in to_iterable(self.bot_checked_keywords) or default_keywords["checked"]):
            self.log.info(f"今日已经签到过了.")
            self._checked = True
            self.finished.set()
        elif any(s in text for s in to_iterable(self.bot_fail_keywords) or default_keywords["fail"]):
            self.log.info(f"签到失败: 验证码错误或网络错误, 正在重试.")
            await self.retry()
        elif any(s in text for s in to_iterable(self.bot_success_keywords) or default_keywords["success"]):
            if await self.before_success():
                if self.bot_success_pat:
                    matches = re.search(self.bot_success_pat, text)
                    if matches:
                        try:
                            self.log.info(
                                f"[yellow]签到成功[/]: + {matches.group(1)} 分 -> {matches.group(2)} 分."
                            )
                        except IndexError:
                            try:
                                self.log.info(f"[yellow]签到成功[/]: 当前/增加 {matches.group(1)} 分.")
                            except IndexError:
                                self.log.info(f"[yellow]签到成功[/].")
                    else:
                        matches = re.search(r"\d+", text)
                        if matches:
                            self.log.info(f"[yellow]签到成功[/]: 当前/增加 {matches.group(0)} 分.")
                        else:
                            self.log.info(f"[yellow]签到成功[/].")
                else:
                    self.log.info(f"[yellow]签到成功[/].")
                await self.after_success()
                self.finished.set()
        else:
            await self.on_unexpected_text(message)

    async def on_unexpected_text(self, message: Message):
        content = message.text or message.caption
        if content:
            spec = content.replace("\n", " ")
            self.log.warning(f"接收到异常返回信息: {spec}, 正在尝试智能回答.")
            if message.reply_markup and message.reply_markup.inline_keyboard:
                buttons = [b.text for r in message.reply_markup.inline_keyboard for b in r]
            else:
                buttons = []
            button_specs = [f"'{b}'" for b in buttons]
            prompt = (
                "我正在进行签到, 机器将显示指令或状态, 我需要通过回答问题以避免被识别为机器人或自动化程序, 并希望完成签到, 现在机器给出的值为:\n\n"
                f"{content}\n\n"
            )
            if buttons:
                prompt += (
                    f"你可选: {', '.join(button_specs)} 中的一个作为回答.\n"
                    "形式为: [CLICK]^XXX^, 其中XXX为回答\n"
                )
            prompt += (
                "如果您认为不应该进行任何操作, 请输出 [NO_RESP], 禁止输出其他内容.\n"
                "如果这是一个指令, 请输出您需要发送或点击的内容.\n"
                "形式为: [SEND]^XXX^, 其中XXX为内容\n"
                "不要说明这是一个指令, 不要说明需要发送文本消息, 仅仅按上述形式输出.\n"
                "如果这是一个状态, 请输出 [IS_STATUS], 禁止输出其他内容."
            )
            for _ in range(3):
                answer, by = await Link(self.client).gpt(prompt)
                if answer:
                    self.log.debug(f"智能回答 ({by}): {answer}")
                    if "[NO_RESP]" in answer:
                        self.log.info(f"智能回答认为无需进行操作, 为了避免风险签到器将停止.")
                        await self.fail()
                        return
                    elif "[IS_STATUS]" in answer:
                        self.log.info(
                            f"智能回答认为这是一条状态信息, 无需进行操作, 为了避免风险签到器将停止."
                        )
                        await self.fail()
                        return
                    elif buttons and "[CLICK]" in answer:
                        self.log.debug(f"当前按钮: {', '.join(button_specs)}")
                        answer_content = re.search(r"\[CLICK\]\^(.+?)\^", answer)
                        if not answer_content:
                            self.log.warning(f"智能回答失败, 为了避免风险签到器将停止.")
                            await self.fail()
                            return
                        answer_content = answer_content.group(1)
                        b, s = process.extractOne(answer_content, buttons, scorer=fuzz.partial_ratio)
                        if s < 70:
                            self.log.info(f"找不到对应回答的按钮, 正在重试.")
                            await asyncio.sleep(3)
                            continue
                        else:
                            try:
                                await message.click(b)
                            except (TimeoutError, MessageIdInvalid):
                                pass
                            self.log.warning(f'智能回答点击了按钮 "{b}", 为了避免风险签到器将停止.')
                            await self.fail()
                            return
                    elif "[SEND]" in answer:
                        answer_content = re.search(r"\[SEND\]\^(.+?)\^", answer)
                        if not answer_content:
                            self.log.warning(f"智能回答失败, 为了避免风险签到器将停止.")
                            await self.fail()
                            return
                        answer_content = answer_content.group(1)
                        await message.reply(answer_content)
                        self.log.warning(f'智能回答回复了 "{answer_content}", 为了避免风险签到器将停止.')
                        await self.fail()
                        return
            else:
                self.log.warning(f"智能回答失败, 为了避免风险签到器将停止.")
                await self.fail()
                return

    async def retry(self):
        """执行重试, 重新发送签到指令."""
        self._retries += 1
        if self._retries <= self.valid_retries:
            await asyncio.sleep(self.bot_retry_wait)
            await self.send_checkin(retry=True)
        else:
            self.log.warning("超过最大重试次数.")
            self.finished.set()

    async def fail(self):
        """设定签到器失败."""
        self._retries = float("inf")
        self.finished.set()

    async def wait_until(self, pattern: str = ".", timeout: float = None):
        """等待特定消息出现."""
        self._waiting[pattern] = e = asyncio.Event()
        try:
            await asyncio.wait_for(e.wait(), timeout)
        except asyncio.TimeoutError:
            return None
        else:
            msg: Message = self._waiting[pattern]
            return msg

    async def before_success(self):
        """签到成功前钩子, 返回值为 True 将继续执行并显示成功信息."""
        return True

    async def after_success(self):
        """签到成功后钩子."""
        pass


class AnswerBotCheckin(BotCheckin):
    """签到类, 用于按钮模式签到."""

    bot_checkin_button_pat: str = None  # 所有按键需要满足的 regex 条件

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.mutex = asyncio.Lock()  # 实例变量异步锁
        self.operable = asyncio.Condition(self.mutex)  # 当 message 被设定时提醒等待的异步线程.
        self.message: Message = None  # 存储可用于回复的带按钮的消息.

    async def walk_history(self, limit=0):
        """处理 limit 条历史消息, 并检测是否有验证码或按钮."""
        try:
            answer = None
            captcha = None
            async for m in self.client.get_chat_history(self.chat_name or self.bot_username, limit=limit):
                if MessageType.ANSWER in self.message_type(m):
                    answer = answer or m
                if MessageType.CAPTCHA in self.message_type(m):
                    captcha = captcha or m
                if answer and captcha:
                    break
            else:
                return False
            await self.on_answer(answer)
            await self.on_photo(captcha)
            return True
        except Exception as e:
            self.log.warning("读取历史消息失败, 将不再读取历史消息.")
            show_exception(e)
            return False

    def get_keys(self, message: Message):
        """获得所有按钮信息."""
        reply_markup = message.reply_markup
        if isinstance(reply_markup, InlineKeyboardMarkup):
            return [k.text for r in reply_markup.inline_keyboard for k in r]
        elif isinstance(reply_markup, ReplyKeyboardMarkup):
            return [k.text for r in reply_markup.keyboard for k in r]

    def is_valid_answer(self, message: Message):
        """确认消息是回复按钮消息."""
        if not message.reply_markup:
            return False
        if self.bot_checkin_button_pat:
            for k in self.get_keys(message):
                if not re.search(self.bot_checkin_button_pat, k):
                    return False
        return True

    def message_type(self, message: Message):
        """分析传入消息的类型为验证码或文字."""
        if self.is_valid_answer(message):
            return MessageType.ANSWER | super().message_type(message)
        else:
            return super().message_type(message)

    async def message_handler(self, client: Client, message: Message, type=None):
        """消息处理入口函数."""
        type = type or self.message_type(message)
        if MessageType.ANSWER in type:
            await self.on_answer(message)
        await super().message_handler(client, message, type=type)

    async def on_answer(self, message: Message):
        """当检测到带按钮的用于回答的消息时保存其信息."""
        async with self.mutex:
            if self.message:
                if self.message.date > message.date:
                    return
                else:
                    self.message = message
            else:
                self.message = message
                self.operable.notify()

    async def on_captcha(self, message: Message, captcha: str):
        """
        可修改的回调函数.
        参数:
            message: 包含验证码图片的消息
            captcha: OCR 识别的验证码
        """
        async with self.operable:
            if not self.message:
                await self.operable.wait()
            match = [(k, fuzz.ratio(k, captcha)) for k in self.get_keys(self.message)]
            max_k, max_r = max(match, key=lambda x: x[1])
            if max_r < 75:
                self.log.info(f'未能找到对应 "{captcha}" 的按键, 正在重试.')
                await self.retry()
            else:
                try:
                    await self.message.click(max_k)
                except (TimeoutError, MessageIdInvalid):
                    pass
