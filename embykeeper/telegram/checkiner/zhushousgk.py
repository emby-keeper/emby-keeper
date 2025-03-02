from . import BotCheckin

__ignore__ = True


class ZhushouSGKCheckin(BotCheckin):
    name = "助手社工库"
    bot_username = "sgk001_bot"
    bot_checkin_cmd = "/checkin"
    bot_checked_keywords = ["今日已签到"]
