from . import BotCheckin

__ignore__ = True


class ByteVirtGroupCheckin(BotCheckin):
    name = "ByteVirt 群组发言"
    chat_name = "bytevirtchat"
    bot_checkin_cmd = ["/showmethemoney"]
    bot_account_fail_keywords = ["未绑定"]
