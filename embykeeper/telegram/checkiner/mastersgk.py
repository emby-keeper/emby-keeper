from . import BotCheckin

__ignore__ = True


class MasterSGKCheckin(BotCheckin):
    name = "Master 社工库"
    bot_username = "BaKaMasterBot"
    bot_checkin_cmd = "/sign"
    checked_retries = 6
