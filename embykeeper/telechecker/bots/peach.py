from pyrogram.types import Message

from .base import BotCheckin


class PeachCheckin(BotCheckin):
    name = "Peach"
    bot_username = "peach_emby_bot"
    bot_checkin_cmd = "/start"
    bot_captcha_len = [2,3,4]
    bot_checkin_caption_pat = "请输入验证码"

    async def message_handler(self, client, message: Message):
        if "欢迎使用" in message.caption and message.reply_markup:
            keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if "签到" in k:
                    await message.click(k)
                    return
        await super().message_handler(client, message)
