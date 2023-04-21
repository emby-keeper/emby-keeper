import asyncio
from typing import List
from .base import AnswerBotCheckin, MessageType

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.handlers import DeletedMessagesHandler


class PornEmbyCheckin(AnswerBotCheckin):
    name = "Pronemby"
    bot_username = "PronembyTGBot2_bot"
    bot_success_pat = r"(\d+).*?(\d+)[^\d]*$"

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._deleted = asyncio.Event()

    def get_handlers(self):
        return [*super().get_handlers(), DeletedMessagesHandler(self.messages_deleted_handler)]

    async def messages_deleted_handler(self, client, messages: List[Message]):
        if self.message:
            for m in messages:
                if self.message.id == m.id:
                    self._deleted.set()
                    return

    async def message_handler(self, client, message: Message, type=None):
        type = type or self.message_type(message)
        if MessageType.ANSWER in type and message.photo:
            await asyncio.sleep(2)
            try:
                self.message = message
                await message.click(0, timeout=1)
            except TimeoutError:
                pass
            try:
                await asyncio.wait_for(self._deleted.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.log.info(f"无响应, 正在重试.")
                await self.retry()
            else:
                await asyncio.sleep(2)
                if not self.finished.is_set():
                    self.log.info(f"今日已经签到过了.")
                    self.finished.set()
            return
        await super().message_handler(client, message, type=type)
