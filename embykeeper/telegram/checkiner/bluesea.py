from . import BotCheckin

__ignore__ = True


class BlueseaCheckin(BotCheckin):
    name = "Bluesea"
    bot_username = "blueseamusic_bot"
    bot_checkin_cmd = ["/cancel", "/checkin"]
    bot_captcha_len = 4
    bot_text_ignore = ["会话已取消", "没有活跃的会话"]
