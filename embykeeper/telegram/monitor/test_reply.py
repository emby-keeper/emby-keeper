from pyrogram.types import Message
from . import Monitor

__ignore__ = True


class TestReplyMonitor(Monitor):
    name = "回复 测试"
    chat_name = "api_group"
    chat_allow_outgoing = True
    chat_keyword = r"回复\s*(\w+)"
    chat_delay = 1

    def chat_reply(self, message: Message, keys):
        return f'接收到: "{keys[0]}"'
