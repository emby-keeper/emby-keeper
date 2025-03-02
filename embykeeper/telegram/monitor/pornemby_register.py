from pyrogram.types import Message
from pyrogram.errors import RPCError

from ..lock import pornemby_alert
from . import Monitor

__ignore__ = True


class PornembyRegisterMonitor(Monitor):
    name = "Pornemby 抢注"
    chat_name = "Pornemby"
    chat_user = "PornembyTGBot_bot"
    chat_keyword = "开 放 注 册"
    additional_auth = ["pornemby_pack"]

    async def on_trigger(self, message: Message, key, reply):
        if pornemby_alert.get(self.client.me.id, False):
            self.log.info(f"由于风险急停不抢注.")
            return
        try:
            await message.click(0)
        except (TimeoutError, RPCError):
            self.log.info("检测到 Pornemby 抢注, 已点击, 请自行查看结果.")
        else:
            self.log.info("检测到 Pornemby 抢注, 已点击, 请自行查看结果.")
