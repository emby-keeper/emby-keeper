import asyncio
import random
import re
from pyrogram.types import Message
from pyrogram.raw.types.messages import BotCallbackAnswer
from pyrogram.errors import MessageIdInvalid

from . import BotCheckin


class PilipiliCheckin(BotCheckin):
    name = "Pilipili"
    bot_username = "PiliPiliUltraTv_bot"
    bot_checkin_caption_pat = "<disabled>"
    bot_checkin_cmd = "/start"
    additional_auth = ["prime"]

    async def message_handler(self, client, message: Message):
        if (
            message.caption
            and ("请选择功能" in message.caption or "用户面板" in message.caption)
            and message.reply_markup
        ):
            keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if "签到" in k:
                    try:
                        answer: BotCallbackAnswer = await message.click(k)
                        await self.on_text(Message(id=0), answer.message)
                    except (TimeoutError, MessageIdInvalid):
                        pass
                    return
            else:
                self.log.warning(f"签到失败: 账户错误.")
                return await self.fail()

        if message.caption and "签到说明" in message.caption:
            text = message.caption.replace("×", "*").replace("÷", "/")
            match = re.search(r"计算出\s*(\d+)\s*([+\-*/])\s*(\d+)\s*=\s*\?", text)
            if match:
                num1, operator, num2 = match.groups()
                num1, num2 = int(num1), int(num2)
                if operator == "+":
                    result = int(num1 + num2)
                elif operator == "-":
                    result = int(num1 - num2)
                elif operator == "*":
                    result = int(num1 * num2)
                elif operator == "/":
                    result = int(num1 / num2)
                self.log.info(f"解析数学题答案: {num1}{operator}{num2}={result}")
                await asyncio.sleep(random.uniform(10, 15))
                await self.client.send_message(self.bot_username, str(result))
                return
            else:
                self.log.warning(f"签到时出现未知题目.")

        if message.text and "请先点击下面加入我们的" in message.text:
            self.log.warning(f"签到失败: 账户错误.")
            return await self.fail()

        await super().message_handler(client, message)
