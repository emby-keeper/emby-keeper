import random

from embykeeper.utils import to_iterable

from . import BotCheckin

__ignore__ = True


class TestGroupCheckin(BotCheckin):
    name = "群组签到测试"
    chat_name = "api_group"
    bot_checkin_cmd = "签到"

    async def send_checkin(self, **kw):
        cmd = random.choice(to_iterable(self.bot_checkin_cmd))
        await self.send(cmd)
        await self.finish(message="群组发言已发送")
