from pyrogram.types import Message

from . import Monitor

__ignore__ = True


class TestPornembyMonitor(Monitor):
    name = "Pornemby 消息接收 测试"
    chat_name = "Pornemby"
    chat_keyword = r".*"

    async def on_trigger(self, message: Message, key, reply):
        self.log.info(f"Pornemby 消息接收 测试: {message.text or message.caption}")
