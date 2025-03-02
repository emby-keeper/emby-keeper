from . import BotCheckin

from pyrogram.types import Message
from pyrogram.errors import MessageIdInvalid

__ignore__ = True


class UnionSGKCheckin(BotCheckin):
    name = "银联社工库"
    bot_username = "unionpaysgkbot"
    bot_checkin_cmd = "/start"
    bot_checked_keywords = ["今日已签到"]

    async def message_handler(self, client, message: Message):
        if message.text and "欢迎使用" in message.text and message.reply_markup:
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
