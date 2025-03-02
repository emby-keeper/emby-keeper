from pyrogram.types import Message
from . import Monitor

__ignore__ = True


class TestGroupMonitor(Monitor):
    name = "多组 测试"
    chat_name = "api_group"
    chat_allow_outgoing = True
    chat_keyword = r"多组\s*(\w+)\s+(\w+)"
    chat_delay = 1

    def chat_reply(self, message: Message, keys):
        return f'接收到: "{keys[0]}" => "{keys[1]}"'
