from ._base import BotCheckin

__ignore__ = True


class InfSGKCheckin(BotCheckin):
    name = "情报局社工库"
    bot_username = "infSGK0_bot"
    bot_checkin_cmd = "/sign"
    bot_success_keywords = ["签到成功"]
    bot_checked_keywords = ["您已经签到过了"]
    checked_retries = 6
