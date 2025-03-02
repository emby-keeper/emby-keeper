from . import BotCheckin

__ignore__ = True


class NiaogeCheckin(BotCheckin):
    name = "鸟哥轰炸"
    bot_username = "nb3344bot"
    bot_checkin_cmd = "/qd"
    additional_auth = ["prime"]
    bot_checked_keywords = "请勿重复签到"
