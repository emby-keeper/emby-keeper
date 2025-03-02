import asyncio
from datetime import datetime

from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

from ..lock import pornemby_nohp, pornemby_messager_enabled

from . import Monitor


class PornembyNoHPMonitor(Monitor):
    name = "Pornemby 血量耗尽停止发言"
    chat_user = ["PronembyTGBot2_bot", "PronembyTGBot3_bot", "PornembyBot", "Porn_Emby_Bot"]
    chat_name = "Pornemby"
    chat_keyword = "(.*)血量已耗尽。"
    additional_auth = ["pornemby_pack"]
    allow_edit = True

    async def on_trigger(self, message: Message, key, reply):
        for me in message.entities:
            if me.type == MessageEntityType.TEXT_MENTION:
                if me.user.id == self.client.me.id:
                    pornemby_nohp[self.client.me.id] = datetime.today().date()
                    self.log.info("检测到 Pornemby 血量耗尽, 已停止今日水群.")

    async def init(self):
        interval = 1
        while True:
            if pornemby_messager_enabled.get(self.client.me.id, False):
                return True
            await asyncio.sleep(interval)
            interval += 1
