from pyrogram.types import Message
from pyrogram.errors import RPCError

from ..lock import pornfans_alert
from . import Monitor

__ignore__ = True


class PornfansRegisterMonitor(Monitor):
    name = "PornFans 抢注"
    chat_name = ["embytestflight", "PornFans_Chat"]
    chat_user = "Porn_Emby_Bot"
    chat_keyword = "开 放 注 册"
    additional_auth = ["pornfans_pack"]

    async def on_trigger(self, message: Message, key, reply):
        if pornfans_alert.get(self.client.me.id, False):
            self.log.info(f"由于风险急停不抢注.")
            return
        try:
            await message.click(0)
        except (TimeoutError, RPCError):
            self.log.info("检测到 PornFans 抢注, 已点击, 请自行查看结果.")
        else:
            self.log.info("检测到 PornFans 抢注, 已点击, 请自行查看结果.")
