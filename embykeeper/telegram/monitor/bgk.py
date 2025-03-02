from pyrogram.types import Message

from . import Monitor


class BGKMonitor(Monitor):
    name = "不给看"
    chat_name = "Ephemeralemby"
    chat_keyword = r"(?:^|\s)([a-zA-Z0-9]{32})(?!\S)"
    bot_username = "UnknownEmbyBot"
    notify_create_name = True
    additional_auth = ["prime"]

    async def on_trigger(self, message: Message, key, reply):
        await self.client.send_message(self.bot_username, "/invite")
        await self.client.send_message(self.bot_username, key)
        await self.client.send_message(self.bot_username, self.unique_name)
        self.log.bind(msg=True).info(f'已向 Bot @{self.bot_username} 发送了邀请码: "{key}", 请查看.')
