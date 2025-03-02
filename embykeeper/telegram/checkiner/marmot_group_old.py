import random

from embykeeper.utils import to_iterable

from . import BotCheckin

__ignore__ = True


class MarmotGroupCheckin(BotCheckin):
    name = "Marmot 群组发言"
    chat_name = -1001975531465
    bot_checkin_cmd = ["签到", "打劫", "没币了", "低保", "打卡", "冒泡"]
    skip = 14

    async def send_checkin(self, **kw):
        cmd = random.choice(to_iterable(self.bot_checkin_cmd))
        await self.send(cmd)
        await self.finish(message="群组发言已发送")
