from . import BotCheckin

__ignore__ = True


class TianmaoSGKCheckin(BotCheckin):
    name = "天猫社工库"
    bot_username = "UISGKbot"
    bot_checkin_cmd = "/sign"
    checked_retries = 6
