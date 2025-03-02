from . import BotCheckin

__ignore__ = True


class HuaSGKCheckin(BotCheckin):
    name = "花花社工库"
    bot_username = "sgkvipbot"
    bot_checkin_cmd = "/sign"
    checked_retries = 6
