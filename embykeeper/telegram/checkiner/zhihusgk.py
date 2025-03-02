from . import BotCheckin

__ignore__ = True


class ZhihuSGKCheckin(BotCheckin):
    name = "知乎社工库"
    bot_username = "zhihu_bot"
    bot_checkin_cmd = "/sign"
    bot_checked_keywords = ["今日已签到"]
