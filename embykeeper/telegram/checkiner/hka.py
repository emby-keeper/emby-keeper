from pyrogram.types import Message
from pyrogram.errors import MessageIdInvalid

from . import BotCheckin

__ignore__ = True


class HKACheckin(BotCheckin):
    name = "HKA"
    bot_username = "hkaemby_bot"
    bot_checkin_cmd = ["/cancel", "/start"]
    bot_text_ignore = ["对话已关闭"]

    async def message_handler(self, client, message: Message):
        text = message.caption or message.text
        if "选择菜单" in text:
            keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if "签到" in k:
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

        if message.text and "未找到绑定用户" in message.text:
            self.log.warning(f"签到失败: 账户错误.")
            return await self.fail()

        await super().message_handler(client, message)
