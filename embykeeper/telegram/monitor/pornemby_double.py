import asyncio
from pyrogram.types import Message, InlineKeyboardMarkup
from pyrogram.enums import MessageEntityType
from pyrogram.errors import RPCError

from ..lock import pornemby_messager_enabled, pornemby_alert
from . import Monitor


class PornembyDoubleMonitor(Monitor):
    name = "Pornemby 怪兽自动翻倍"
    chat_user = ["PronembyTGBot2_bot", "PronembyTGBot3_bot", "PornembyBot", "Porn_Emby_Bot"]
    chat_name = "Pornemby"
    chat_keyword = r"击杀者\s+(.*)\s+是否要奖励翻倍"
    additional_auth = ["pornemby_pack"]
    allow_edit = True

    async def on_trigger(self, message: Message, key, reply):
        if pornemby_alert.get(self.client.me.id, False):
            self.log.info(f"由于风险急停不翻倍.")
            return
        for me in message.entities:
            if me.type == MessageEntityType.TEXT_MENTION:
                if me.user.id == self.client.me.id:
                    if isinstance(message.reply_markup, InlineKeyboardMarkup):
                        try:
                            await message.click("🎲开始翻倍游戏")
                        except RPCError:
                            pass
                        else:
                            self.log.info("检测到 Pornemby 怪兽击败, 已点击翻倍.")
                            return

    async def init(self):
        interval = 1
        while True:
            if pornemby_messager_enabled.get(self.client.me.id, False):
                return True
            await asyncio.sleep(interval)
            interval += 1
