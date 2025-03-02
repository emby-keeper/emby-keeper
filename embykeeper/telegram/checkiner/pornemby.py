import asyncio
import random

from pyrogram.types import Message
from pyrogram.errors import BadRequest, MessageIdInvalid

from . import AnswerBotCheckin


class PornembyCheckin(AnswerBotCheckin):
    name = "Pornemby"
    bot_username = "Porn_Emby_Bot"
    bot_success_pat = r".*?(\d+)$"

    async def on_photo(self, message: Message):
        await asyncio.sleep(random.uniform(2, 4))
        async with self.client.catch_reply(self.bot_username) as f:
            try:
                await message.click("点击签到")
            except (TimeoutError, MessageIdInvalid):
                pass
            except BadRequest:
                self.log.warning(f"签到失败: 账户错误.")
                await self.fail()
            try:
                m = await asyncio.wait_for(f, 10)
            except asyncio.TimeoutError:
                self.log.warning(f"签到失败: 签到无回应, 您可能还没有注册 {self.name} Emby 账号.")
                await self.fail()
            else:
                return await self.on_text(m, m.text)
