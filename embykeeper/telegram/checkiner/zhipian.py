from . import BotCheckin

__ignore__ = True


class ZhipianCheckin(BotCheckin):
    name = "纸片"
    bot_username = "zhipianbot"
    bot_checkin_cmd = "/qd"
    additional_auth = ["prime"]
    checked_retries = 6
