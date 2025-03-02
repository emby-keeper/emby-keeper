from . import BotCheckin

__ignore__ = True


class FeijiCheckin(BotCheckin):
    name = "飞机工具箱"
    bot_username = "fjtool_bot"
    bot_checkin_cmd = "/signin"
    additional_auth = ["prime"]
