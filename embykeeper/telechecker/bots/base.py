import asyncio
import re
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager, suppress
from enum import Flag, auto

import ddddocr
from loguru import logger
from PIL import Image
from pyrogram import filters
from pyrogram.errors import UsernameNotOccupied
from pyrogram.handlers import EditedMessageHandler, MessageHandler
from pyrogram.types import InlineKeyboardMarkup, Message, ReplyKeyboardMarkup
from thefuzz import fuzz

from ...utils import AsyncCountPool, to_iterable
from ..tele import Client

ocr = ddddocr.DdddOcr(beta=True, show_ad=False)


class MessageType(Flag):
    TEXT = auto()
    CAPTION = auto()
    CAPTCHA = auto()
    ANSWER = auto()


class BaseBotCheckin(ABC):
    name = __name__

    def __init__(self, client: Client, retries=10, timeout=60, nofail=True, captcha_service='disabled', captcha_service_key='empty'):
        self.client = client
        self.retries = retries
        self.timeout = timeout
        self.nofail = nofail
        self.captcha_service = captcha_service
        self.captcha_service_key = captcha_service_key
        self.finished = asyncio.Event()
        self.log = logger.bind(scheme="telechecker", name=self.name, username=self.client.me.first_name)

    async def _start(self):
        try:
            return await self.start()
        except Exception as e:
            if self.nofail:
                self.log.opt(exception=e).warning(f"初始化错误:")
                return False
            else:
                raise

    @abstractmethod
    async def start(self):
        pass


class BotCheckin(BaseBotCheckin):
    group_pool = AsyncCountPool(base=1000)
    bot_id = None
    bot_username = None
    bot_checkin_cmd = ["/checkin"]
    bot_checkin_caption_pat = None
    bot_text_ignore = []
    bot_captcha_len = range(2, 7)
    bot_success_pat = r"(\d+)[^\d]*(\d+)"
    bot_use_history = None
    chat_name = None

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._is_archived = False
        self._retries = 0

    @asynccontextmanager
    async def listener(self):
        filter = filters.user(self.bot_id or self.bot_username)
        if self.chat_name:
            filter = filter & filters.chat(self.chat_name)
        handlers = [
            MessageHandler(self._message_handler, filter),
            EditedMessageHandler(self._message_handler, filter),
        ]
        group = await BotCheckin.group_pool.append(handlers)
        for h in handlers:
            self.client.add_handler(h, group=group)
        yield
        for h in handlers:
            try:
                self.client.remove_handler(h, group=group)
            except ValueError:
                pass

    async def wait_finished(self, chat):
        await self.finished.wait()
        if self._is_archived:
            await chat.archive()

    async def start(self):
        ident = self.chat_name or self.bot_id or self.bot_username
        try:
            chat = await self.client.get_chat(ident)
        except UsernameNotOccupied:
            self.log.warning(f'初始化错误: 会话 "{ident}" 不存在.')
            return False
        async for d in self.client.get_dialogs(folder_id=1):
            if d.chat.id == chat.id:
                self._is_archived = True
                break
        bot = await self.client.get_users(self.bot_id or self.bot_username)
        msg = f"开始执行签到: [green]{bot.first_name}[/] [gray50](@{bot.username})[/]"
        if chat.title:
            msg += f" @ [green]{chat.title}[/] [gray50](@{chat.username})[/]"
        self.log.info(msg + ".")
        asyncio.create_task(self.wait_finished(chat))
        try:
            async with self.listener():
                if self.bot_use_history is None:
                    await self.send_checkin()
                elif not await self.walk_history(self.bot_use_history):
                    await self.send_checkin()
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self.finished.wait(), self.timeout)
        except OSError as e:
            self.log.warning(f'初始化错误: "{e}".')
            return False
        if not self.finished.is_set():
            self.log.warning("无法在时限内完成签到.")
            return False
        else:
            return self._retries <= self.retries

    async def walk_history(self, limit=0):
        async for m in self.client.get_chat_history(
            self.chat_name or self.bot_id or self.bot_username, limit=limit
        ):
            if MessageType.CAPTCHA in self.message_type(m):
                await self.on_photo(m)
                return True
        return False

    async def send(self, cmd):
        if self.chat_name:
            bot = await self.client.get_users(self.bot_id or self.bot_username)
            await self.client.send_message(self.chat_name, f"{cmd}@{bot.username}")
        else:
            await self.client.send_message(self.bot_id or self.bot_username, cmd)

    async def send_checkin(self):
        for cmd in to_iterable(self.bot_checkin_cmd):
            await self.send(cmd)
            await asyncio.sleep(5)

    async def _message_handler(self, *args, **kw):
        try:
            await self.message_handler(*args, **kw)
        except OSError as e:
            self.log.info(f'发生错误: "{e}", 正在重试.')
            await self.retry()
        except Exception as e:
            self.finished.set()
            if self.nofail:
                self.log.opt(exception=e).warning(f"发生错误:")
            else:
                raise

    async def message_handler(self, client: Client, message: Message, type=None):
        type = type or self.message_type(message)
        if MessageType.TEXT in type:
            await self.on_text(message, message.text)
        if MessageType.CAPTION in type:
            await self.on_text(message, message.caption)
        if MessageType.CAPTCHA in type:
            await self.on_photo(message)

    def message_type(self, message: Message):
        if message.photo:
            if message.caption:
                if self.bot_checkin_caption_pat:
                    if re.search(self.bot_checkin_caption_pat, message.caption):
                        return MessageType.CAPTCHA
                    else:
                        return MessageType.CAPTION
                else:
                    return MessageType.CAPTCHA
            else:
                return MessageType.CAPTCHA
        elif message.text:
            return MessageType.TEXT

    async def on_photo(self, message: Message):
        data = await self.client.download_media(message, in_memory=True)
        image = Image.open(data)
        captcha = ocr.classification(image).replace(" ", "")
        if len(captcha) not in to_iterable(self.bot_captcha_len):
            self.log.info(f'验证码 "{captcha}" 低于设定长度, 正在重试.')
            await self.retry()
        else:
            await asyncio.sleep(1)
            await self.on_captcha(message, captcha)

    async def on_captcha(self, message: Message, captcha: str):
        self.log.debug(f"接收到验证码: {captcha}")
        await message.reply(captcha)

    async def on_text(self, message: Message, text: str):
        if any(s in text for s in to_iterable(self.bot_text_ignore)):
            pass
        elif any(s in text for s in ("失败", "错误", "超时")):
            self.log.info(f"签到失败, 正在重试.")
            await self.retry()
        elif any(s in text for s in ("成功", "通过", "完成")):
            matches = re.search(self.bot_success_pat, text)
            if matches:
                self.log.info(f"[yellow]签到成功[/]: + {matches.group(1)} 分 -> {matches.group(2)} 分.")
            else:
                matches = re.search(r"\d+", text)
                if matches:
                    self.log.info(f"[yellow]签到成功[/]: 当前 {matches.group(0)} 分.")
                else:
                    self.log.info(f"[yellow]签到成功[/].")
            self.finished.set()
        elif any(s in text for s in ("只能", "已经", "下次", "过了", "签过")):
            self.log.info(f"今日已经签到过了.")
            self.finished.set()
        else:
            self.log.warning(f"接收到异常返回信息: {text}")

    async def retry(self):
        self._retries += 1
        if self._retries <= self.retries:
            await asyncio.sleep(5)
            await self.send_checkin()
        else:
            self.log.warning("超过最大重试次数.")
            self.finished.set()


class AnswerBotCheckin(BotCheckin):
    bot_checkin_button_pat = None

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.mutex = asyncio.Lock()
        self.operable = asyncio.Condition(self.mutex)
        self.message: Message = None

    async def walk_history(self, limit=0):
        answer = None
        captcha = None
        async for m in self.client.get_chat_history(
            self.chat_name or self.bot_id or self.bot_username, limit=limit
        ):
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

    def get_keys(self, message: Message):
        reply_markup = message.reply_markup
        if isinstance(reply_markup, InlineKeyboardMarkup):
            return [k.text for r in reply_markup.inline_keyboard for k in r]
        elif isinstance(reply_markup, ReplyKeyboardMarkup):
            return [k.text for r in reply_markup.keyboard for k in r]

    def is_valid_answer(self, message: Message):
        if not message.reply_markup:
            return False
        if self.bot_checkin_button_pat:
            for k in self.get_keys(message):
                if not re.search(self.bot_checkin_button_pat, k):
                    return False
        return True

    def message_type(self, message: Message):
        if self.is_valid_answer(message):
            return MessageType.ANSWER | super().message_type(message)
        else:
            return super().message_type(message)

    async def message_handler(self, client: Client, message: Message):
        type = self.message_type(message)
        if MessageType.ANSWER in type:
            await self.on_answer(message)
        await super().message_handler(client, message, type=type)

    async def on_answer(self, message: Message):
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
        async with self.operable:
            if not self.message:
                await self.operable.wait()
            match = [(k, fuzz.ratio(k, captcha)) for k in self.get_keys(self.message)]
            max_k, max_r = max(match, key=lambda x: x[1])
            if max_r < 75:
                self.log.info(f'未能找到对应 "{captcha}" 的按键, 正在重试.')
                await self.retry()
            else:
                await self.message.click(max_k)
