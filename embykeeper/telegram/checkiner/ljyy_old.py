from pyrogram.types import Message
from pyrogram.errors import RPCError
from thefuzz import fuzz

from . import AnswerBotCheckin

__ignore__ = True


class LJYYCheckin(AnswerBotCheckin):
    ocr = "uchars4@v1"

    name = "垃圾影音"
    bot_username = "zckllflbot"
    bot_captcha_len = 4
    bot_use_history = 20
    bot_text_ignore = "下列选项"

    async def retry(self):
        if self.message:
            try:
                await self.message.click()
            except (RPCError, TimeoutError):
                pass
        await super().retry()

    async def on_captcha(self, message: Message, captcha: str):
        async with self.operable:
            if not self.message:
                await self.operable.wait()
            match = [(k, fuzz.ratio(k, captcha)) for k in self.get_keys(self.message)]
            max_k, max_r = max(match, key=lambda x: x[1])
            await self.message.click(max_k)
