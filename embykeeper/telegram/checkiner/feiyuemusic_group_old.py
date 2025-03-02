import random
from embykeeper.utils import to_iterable
from . import BotCheckin

__ignore__ = True


class FeiyueMusicGroupCheckin(BotCheckin):
    name = "飞跃星空群组发言"
    chat_name = -1002197507537
    bot_checkin_cmd = "签到"
    skip = 14

    async def send_checkin(self, **kw):
        cmd = random.choice(to_iterable(self.bot_checkin_cmd))
        await self.send(cmd)
        await self.finish(message="群组发言已发送")
