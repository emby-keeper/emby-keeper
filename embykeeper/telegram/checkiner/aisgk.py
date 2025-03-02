from . import BotCheckin

__ignore__ = True


class AISGKCheckin(BotCheckin):
    name = "AI 社工库"
    bot_username = "aishegongkubot"
    bot_checkin_cmd = "/sign"
    bot_checked_keywords = "请勿重复签到"
