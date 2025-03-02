from . import BotCheckin

__ignore__ = True


class AkileCheckin(BotCheckin):
    name = "Akile"
    bot_username = "akilecloud_bot"
    bot_account_fail_keywords = ["未绑定"]
