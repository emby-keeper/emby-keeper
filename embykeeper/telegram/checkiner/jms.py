import httpx
from pyrogram.types import Message
from pyrogram.raw.functions.messages import AcceptUrlAuth
from pyrogram.raw.types import UrlAuthResultAccepted
from faker import Faker

from embykeeper.utils import get_proxy_str
from embykeeper.config import config

from . import BotCheckin

__ignore__ = True


class JMSCheckin(BotCheckin):
    name = "卷毛鼠"
    bot_username = "jmsembybot"
    bot_checked_keywords = "请明天再来签到"

    async def message_handler(self, client, message: Message):
        if message.reply_markup:
            keys = [k for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if "点我签到" in k.text:
                    r: UrlAuthResultAccepted = await self.client.invoke(
                        AcceptUrlAuth(
                            peer=await self.client.resolve_peer(message.chat.id),
                            msg_id=message.id,
                            button_id=k.login_url.button_id,
                            url=k.login_url.url,
                        )
                    )
                    url = r.url
                    for _ in range(1, 3):
                        async with httpx.AsyncClient(
                            http2=True, proxies=get_proxy_str(config.proxy)
                        ) as client:
                            resp = await client.get(url, headers={"User-Agent": Faker().safari()})
                            if resp.status_code == 200:
                                return
        return await super().message_handler(client, message)
