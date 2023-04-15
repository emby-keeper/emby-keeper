from .base import AnswerBotCheckin

from pyrogram.errors import BadRequest

class pornCheckin(AnswerBotCheckin):
    name = "PronembyTGBot2_bot"
    bot_username = "PronembyTGBot2_bot"
    bot_captcha_len = 2
    async def retry(self):
            if self.message:
                try:
                    await self.message.click(0)
                except (BadRequest, TimeoutError):
                    pass
            await super().retry()