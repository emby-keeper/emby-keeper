from . import BotCheckin

__ignore__ = True


class DogSGKCheckin(BotCheckin):
    name = "狗狗社工库"
    bot_username = "DogeSGK_bot"
    bot_checkin_cmd = "/sign"
    bot_success_pat = r".*\+(\d+)"
    bot_checked_keywords = "请勿重复签到"
