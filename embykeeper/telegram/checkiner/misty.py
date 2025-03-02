import asyncio
import random

from pyrogram.types import Message

from embykeeper.utils import async_partial

from ..lock import misty_monitors, misty_locks
from . import BotCheckin


class MistyCheckin(BotCheckin):
    ocr = "digit5-large@v1"

    name = "Misty"
    bot_username = "EmbyMistyBot"
    bot_captcha_len = 5
    bot_checkin_caption_pat = "请输入验证码"
    bot_text_ignore = ["选择您要使用的功能", "欢迎使用", "选择功能"]
    bot_checked_keywords = ["距离上次签到未过"]
    additional_auth = ["super"]

    async def start(self):
        misty_locks.setdefault(self.client.me.id, asyncio.Lock())
        lock = misty_locks.get(self.client.me.id, None)
        async with lock:
            return await super().start()

    async def send_checkin(self, retry=False):
        wr = async_partial(self.client.wait_reply, self.bot_username)
        for _ in range(3):
            try:
                msg: Message = await wr("/cancel")
                if "选择您要使用的功能" in (msg.caption or msg.text):
                    await asyncio.sleep(random.uniform(2, 4))
                    msg = await wr("🎲更多功能")
                if "请选择功能" in (msg.text or msg.caption):
                    await asyncio.sleep(random.uniform(2, 4))
                    msg = await wr("🛎每日签到")
                    if "获取账号失败" in (msg.text or msg.caption):
                        self.log.warning(f"签到失败: 未注册账号.")
                        return await self.fail()
                    else:
                        return await self.message_handler(self.client, msg)
            except asyncio.TimeoutError:
                pass
        else:
            self.log.warning(f"签到失败: 无法进入签到页面.")
            await self.fail()

    async def cleanup(self):
        monitor = misty_monitors.get(self.client.me.id, None)
        if monitor:
            if not await monitor.init():
                self.log.warning(f"发生冲突: 无法重置 Misty 开注监控状态.")
                return False
        return True
