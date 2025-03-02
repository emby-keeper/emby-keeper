from . import BotCheckin

__ignore__ = True


class MoshenSGKCheckin(BotCheckin):
    name = "魔神社工库"
    bot_username = "moshensgk_bot"
    bot_checkin_cmd = "/qd"
    max_retries = 6
