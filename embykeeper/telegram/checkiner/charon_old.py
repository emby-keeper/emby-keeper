import asyncio

from . import BotCheckin

__ignore__ = True


class CharonCheckin(BotCheckin):
    name = "卡戎"
    ocr = "words6@v1"
    bot_username = "charontv_bot"
    bot_checkin_cmd = ["/checkin", "/cancel"]
    bot_captcha_len = 6
    bot_success_pat = r".*(\d+)"
    bot_text_ignore = ["已结束当前对话"]

    async def send_checkin(self, retry=False):
        if retry:
            await asyncio.sleep(self.bot_send_interval)
        while True:
            await self.send("/checkin")
            if await self.wait_until("已结束当前对话", 3):
                continue
            else:
                break
