from . import BotCheckin

__ignore__ = True


class AkileGroupCheckin(BotCheckin):
    name = "Akile 群组发言"
    chat_name = "akileChat"
    bot_checkin_cmd = ["/checkin@akilecloud_bot"]
    bot_account_fail_keywords = ["未绑定"]
