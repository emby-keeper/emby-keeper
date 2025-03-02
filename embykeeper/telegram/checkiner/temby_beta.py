from .temby import TembyCheckin

__ignore__ = True


class TembyBetaCheckin(TembyCheckin):
    name = "Temby"
    bot_username = "Temby_Bot"
    bot_account_fail_keywords = ["需要内测码"]
