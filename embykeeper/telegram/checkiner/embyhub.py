from . import BotCheckin

__ignore__ = True


class EmbyHubCheckin(BotCheckin):
    name = "EmbyHub"
    bot_username = "EdHubot"
    bot_checked_keywords = ["今日已签到"]
