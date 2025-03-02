from . import BotCheckin

__ignore__ = True


class StarSGKCheckin(BotCheckin):
    name = "星月社工库"
    bot_username = "XY_SGKBOT"
    bot_checkin_cmd = "/sign"
    checked_retries = 6
