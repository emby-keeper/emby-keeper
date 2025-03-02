import asyncio
import random
from pyrogram.types import Message

from embykeeper.utils import async_partial

from . import Monitor

__ignore__ = True


class JudogMonitor(Monitor):
    name = "剧狗"
    chat_name = "Mulgoreemby"
    chat_keyword = r"剩余可注册人数：\d+"
    bot_username = "mulgorebot"
    notify_create_name = True
    additional_auth = ["prime"]

    async def init(self):
        channel = await self.client.get_chat("Mulgoreemby")
        if channel and channel.linked_chat:
            self.chat_name = channel.linked_chat.id
            self.log.info(f"已读取剧狗频道关联群: {channel.linked_chat.title}")
            return True
        else:
            self.log.warning(f"没有找到关联群.")
            return False

    async def on_trigger(self, message: Message, key, reply):
        wr = async_partial(self.client.wait_reply, self.bot_username)
        msg: Message = await wr("/start")
        if "选择您要使用的功能" in (msg.caption or msg.text):
            await asyncio.sleep(random.uniform(2, 4))
            msg = await wr("🔱账号")
        if "账号管理中心" in (msg.caption or msg.text):
            await asyncio.sleep(random.uniform(2, 4))
            msg = await wr("💡注册")
        if "目前已无可注册资格" in (msg.caption or msg.text):
            return
        else:
            self.log.bind(msg=True).info(
                f'已向 Bot @{self.bot_username} 发送了用户注册申请: "{self.unique_name}", 请检查结果.'
            )
