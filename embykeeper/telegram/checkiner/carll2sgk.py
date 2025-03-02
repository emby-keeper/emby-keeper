from . import BotCheckin

from pyrogram.types import Message
from pyrogram.errors import MessageIdInvalid

__ignore__ = True


class Carll2SGKCheckin(BotCheckin):
    name = "Carll 社工库 2"
    bot_username = "Carllnet2_bot"
    bot_checkin_cmd = "/qd"

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
