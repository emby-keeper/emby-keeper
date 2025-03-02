from . import BotCheckin

__ignore__ = True


class SeedSGKCheckin(BotCheckin):
    name = "Seed 社工库"
    bot_username = "SeedSGKBOT"
    bot_checkin_cmd = "/sign"
    bot_checked_keywords = ["今日已签到"]
