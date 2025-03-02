from pyrogram.types import Message

from . import Monitor


class InfinityFlyMonitor(Monitor):
    name = "Infinity Fly"
    chat_keyword = r"register-[-\w]{36}"
    bot_username = "Infinity94bot"
    chat_name = "infinityfly664"
    notify_create_name = True
    allow_edit = False
    additional_auth = ["prime"]

    async def on_trigger(self, message: Message, key, reply):
        await self.client.send_message(self.bot_username, f"/invite {key}")
        await self.client.send_message(self.bot_username, f"/create {self.unique_name}")
        self.log.bind(msg=True).info(f'已向 Bot @{self.bot_username} 发送了邀请码: "{key}", 请查看.')
