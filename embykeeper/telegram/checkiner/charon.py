import asyncio
import re

from pyrogram import Client
from pyrogram.types import Message
from ..link import Link
from . import BotCheckin

__ignore__ = True


class CharonCheckin(BotCheckin):
    name = "卡戎"
    bot_username = "charontv_bot"
    bot_success_pat = r".*(\d+)"
    bot_text_ignore = ["已结束当前对话"]
    additional_auth = ["captcha"]
    bot_success_keywords = ["签到成功"]
    bot_fail_keywords = ["购买账号"]

    async def send_checkin(self, retry=False):
        if retry:
            await asyncio.sleep(self.bot_send_interval)
        while True:
            await self.send("/checkin")
            if await self.wait_until("已结束当前对话", 3):
                await asyncio.sleep(self.bot_send_interval)
                continue
            else:
                break

    async def message_handler(self, client: Client, message: Message):
        if message.text:
            match = re.search(r"请打开并复制网页的内容, 粘贴回复:\s*(.*)", message.text)
            if match:
                return await self.handle_url(match.group(1))
        return await super().message_handler(client, message)

    async def handle_url(self, url: str):
        self.log.debug(f"即将解析网页中的验证码: {url}.")
        for i in range(3):
            result = await Link(self.client).captcha_content("charon", url)
            if result:
                await self.client.send_message(self.bot_username, result)
                break
            else:
                self.log.warning(f"正在重试解析验证码 ({i+1} / 3).")
