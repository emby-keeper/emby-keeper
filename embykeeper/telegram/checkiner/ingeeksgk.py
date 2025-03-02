from . import BotCheckin

__ignore__ = True


class IngeekSGKCheckin(BotCheckin):
    name = "Ingeek 社工库"
    bot_username = "ingeeksgkbot"
    bot_checkin_cmd = "/checkin"
    bot_checked_keywords = ["今日已签到"]
