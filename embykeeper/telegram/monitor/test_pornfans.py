from pyrogram.types import Message

from . import Monitor

__ignore__ = True


class TestPornfansMonitor(Monitor):
    name = "PornFans 消息接收 测试"
    chat_name = "Porn_Emby_Bot"
    chat_keyword = r".*"

    async def on_trigger(self, message: Message, key, reply):
        self.log.info(f"PornFans 消息接收 测试: {message.text or message.caption}")
