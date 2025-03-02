from . import BotCheckin

__ignore__ = True


class BostSGKCheckin(BotCheckin):
    name = "Bost 社工库"
    bot_username = "BOST_SGK_BOT"
    bot_checkin_cmd = "/qd"
    bot_use_captcha = False
