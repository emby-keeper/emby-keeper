import asyncio
import random
import string

from thefuzz import process
from pyrogram.types import Message
from pyrogram.errors import MessageIdInvalid

from ..link import Link
from . import BotCheckin


class CCCheckin(BotCheckin):
    name = "CC公益"
    bot_username = "EmbyCc_bot"
    bot_checkin_cmd = "/start"
    bot_checked_keywords = ["已经签到过了"]
    bot_checkin_caption_pat = "请选择正确验证码"
    max_retries = 1
    additional_auth = ["ocr"]

    async def message_handler(self, client, message: Message):
        if message.caption and "欢迎使用" in message.caption and message.reply_markup:
            keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if "签到" in k:
                    try:
                        await message.click(k)
                    except (TimeoutError, MessageIdInvalid):
                        pass
                    return
            else:
                self.log.warning(f"签到失败: 账户错误.")
                return await self.fail()
        await super().message_handler(client, message)

    async def on_photo(self, message: Message):
        """分析分析传入的验证码图片并返回验证码."""
        if not message.reply_markup:
            return
        for i in range(3):
            result: str = await Link(self.client).ocr(message.photo.file_id)
            if result:
                self.log.debug(f"远端已解析答案: {result}.")
                break
            else:
                self.log.warning(f"远端解析失败, 正在重试解析 ({i + 1}/3).")
        else:
            self.log.warning(f"签到失败: 验证码识别错误.")
            return await self.fail()
        options = [k.text for r in message.reply_markup.inline_keyboard for k in r]
        result = result.translate(str.maketrans("", "", string.punctuation)).replace(" ", "")
        captcha, score = process.extractOne(result, options)
        if score < 50:
            self.log.warning(f"远端答案难以与可用选项相匹配 (分数: {score}/100).")
        self.log.debug(f"[gray50]接收验证码: {captcha}.[/]")
        await asyncio.sleep(random.uniform(2, 4))
        try:
            await message.click(captcha)
        except (TimeoutError, MessageIdInvalid):
            pass
