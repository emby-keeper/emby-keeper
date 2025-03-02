import asyncio
from pyrogram.types import Message

from . import Monitor

__ignore__ = True


class PoloMonitor(Monitor):
    name = "Polo"
    chat_name = "poloemby"
    chat_keyword = r"普通可用的注册码:\n([\s\S]*)"
    bot_username = "polo_emby_bot"
    notify_create_name = True
    additional_auth = ["prime"]

    async def on_trigger(self, message: Message, key, reply):
        for code in key.split("\n"):
            await self.client.send_message(self.bot_username, f"/invite {code}")
            await self.client.send_message(self.bot_username, self.unique_name)
            await asyncio.sleep(0.5)
            self.log.bind(msg=True).info(f'已向 Bot @{self.bot_username} 发送了邀请码: "{code}", 请查看.')
