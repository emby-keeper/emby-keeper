import random
from pyrogram.types import Message, InlineKeyboardMarkup
from pyrogram.errors import RPCError
from pyrogram.enums import MessageEntityType

from embykeeper.utils import flatten

from ..lock import pornfans_alert
from . import Monitor


class PornfansDragonRainMonitor:
    class PornfansDragonRainClickMonitor(Monitor):
        name = "PornFans 红包雨"
        chat_user = ["Porn_Emby_Bot", "Porn_emby_ScriptsBot"]
        chat_name = ["embytestflight", "PornFans_Chat"]
        chat_keyword = [None]
        additional_auth = ["pornfans_pack"]
        allow_edit = True
        debug_no_log = True

        async def on_trigger(self, message: Message, key, reply):
            if pornfans_alert.get(self.client.me.id, False):
                self.log.info(f"由于风险急停不抢红包.")
                return
            if message.reply_markup:
                if isinstance(message.reply_markup, InlineKeyboardMarkup):
                    buttons = flatten(message.reply_markup.inline_keyboard)
                    for b in buttons:
                        if "红包奖励" in b.text:
                            if random.random() > self.config.get("possibility", 1.0):
                                self.log.info(f"由于概率设置不抢红包.")
                                return
                            try:
                                await message.click(b.text)
                            except (TimeoutError, RPCError):
                                self.log.info("检测到 PornFans 抢红包雨, 已点击抢红包, 等待结果.")
                            else:
                                self.log.info("检测到 PornFans 抢红包雨, 已点击抢红包, 等待结果.")
                            return

    class PornfansDragonRainStatusMonitor(Monitor):
        name = "PornFans 红包雨结果"
        chat_user = ["Porn_Emby_Bot", "Porn_emby_ScriptsBot"]
        chat_name = ["embytestflight", "PornFans_Chat"]
        chat_keyword = r"恭喜\s+(.*):本次获得(\d+)豆"
        allow_edit = True

        async def on_trigger(self, message: Message, key, reply):
            for me in message.entities:
                if me.type == MessageEntityType.TEXT_MENTION:
                    if me.user.id == self.client.me.id:
                        self.log.info(f"红包雨结果: 恭喜获得 {key[1]} 豆.")
