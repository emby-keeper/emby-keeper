from . import BotCheckin

__ignore__ = True


class OixelCheckin(BotCheckin):
    name = "Oixel"
    bot_username = "oixel_bot"
    bot_checkin_cmd = "📅 签到"
    additional_auth = ["prime"]
    max_retries = 6
