import asyncio

from pyrogram.types import Message
from pyrogram.errors import MessageIdInvalid
from thefuzz import fuzz

from . import AnswerBotCheckin

__ignore__ = True


class LJYYCheckin(AnswerBotCheckin):
    ocr = "uchars4@v1"

    name = "垃圾影音"
    bot_username = "zckllflbot"
    bot_checkin_cmd = ["/stop", "/cz"]
    bot_use_history = 20
    bot_text_ignore = ["下列选项", "退出流程"]
    bot_checkin_button_pat = r"\w\s\w\s\w\s\w"
    additional_auth = ["prime"]

    async def message_handler(self, client, message: Message):
        if message.text and "请选择操作项" in message.text and message.reply_markup:
            keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if "签到" in k:
                    async with self.client.catch_reply(self.bot_username) as f:
                        try:
                            await message.click(k)
                        except (TimeoutError, MessageIdInvalid):
                            pass
                        try:
                            await asyncio.wait_for(f, 10)
                        except asyncio.TimeoutError:
                            self.log.warning(f"签到失败: 点击签到无响应.")
                            await self.fail()
            else:
                self.log.warning(f"签到失败: 账户错误.")
                return await self.fail()
        await super().message_handler(client, message)

    async def on_captcha(self, message: Message, captcha: str):
        async with self.operable:
            if not self.message:
                await self.operable.wait()
            match = [(k, fuzz.ratio(k, captcha)) for k in self.get_keys(self.message)]
            max_k, max_r = max(match, key=lambda x: x[1])
            self.log.info(f"识别字符: {captcha}, 选择字符: {max_k}")
            await self.message.click(max_k)
