from pyrogram.types import Message

from .base import BotCheckin


class BlueseaCheckin(BotCheckin):
    name = "Bluesea"
    bot_username = "blueseamusic_bot"
    bot_checkin_cmd = ["/cancel", "/checkin"]
    bot_text_ignore = ["会话已取消", "没有活跃的会话"]
    bot_captcha_len = 4
