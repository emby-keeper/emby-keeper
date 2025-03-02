from pyrogram.types import Message
from pyrogram.errors import MessageIdInvalid

from . import BotCheckin

__ignore__ = True


class M78Checkin(BotCheckin):
    name = "M78 星云"
    bot_username = "M78CheckIn_bot"
    bot_success_pat = None

    async def message_handler(self, client, message: Message):
        text = message.caption or message.text
        if text and "欢迎来到M78星云" in text and message.reply_markup:
            keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if "签到" in k or "簽到" in k:
                    try:
                        await message.click(k)
                    except TimeoutError:
                        self.log.debug(f"点击签到按钮无响应, 可能按钮未正确处理点击回复. 一般来说不影响签到.")
                    except MessageIdInvalid:
                        pass
                    return
            else:
                self.log.warning(f"签到失败: 账户错误.")
                return await self.fail()

        if message.text and "请先绑定" in message.text:
            self.log.warning(f"签到失败: 账户错误.")
            return await self.fail()

        await super().message_handler(client, message)
