import asyncio
from pyrogram.types import Message
from pyrogram import filters
from pyrogram.errors import MessageIdInvalid

from embykeeper.utils import async_partial

from . import Monitor

__ignore__ = True


class ShufuMonitor(Monitor):
    name = "叔服"
    chat_name = -1001890341413
    chat_keyword = r"SHUFU-\d+-Register_[\w]+"
    bot_username = "dashu660_bot"
    notify_create_name = True
    additional_auth = ["prime"]

    async def on_trigger(self, message: Message, key, reply):
        wr = async_partial(self.client.wait_reply, self.bot_username)
        for _ in range(3):
            try:
                msg = await wr("/start")
                if "请确认好重试" in (msg.text or msg.caption):
                    continue
                elif "欢迎进入用户面板" in (msg.text or msg.caption) and msg.reply_markup:
                    keys = [k.text for r in msg.reply_markup.inline_keyboard for k in r]
                    for k in keys:
                        if "使用注册码" in k:
                            async with self.client.catch_reply(
                                self.bot_username, filter=filters.regex(".*对我发送.*")
                            ) as f:
                                try:
                                    await msg.click(k)
                                except (TimeoutError, MessageIdInvalid):
                                    pass
                                try:
                                    await asyncio.wait_for(f, 10)
                                except asyncio.TimeoutError:
                                    continue
                                else:
                                    break
                    else:
                        continue
                    msg = await wr(key)
                    if "注册码已被使用" in (msg.text or msg.caption):
                        self.log.info(f'已向 Bot @{self.bot_username} 发送了邀请码: "{key}", 但是已被抢注了.')
                    else:
                        self.log.bind(msg=True).info(
                            f'已向 Bot @{self.bot_username} 发送了邀请码: "{key}", 请查看.'
                        )
                    break
                else:
                    continue
            except asyncio.TimeoutError:
                pass
        else:
            self.log.bind(msg=True).warning(f"已监控到{self.name}的邀请码, 但自动使用失败, 请自行查看.")
