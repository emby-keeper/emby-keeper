import random

from embykeeper.utils import to_iterable

from . import BotCheckin


class PandaTVGroupCheckin(BotCheckin):
    name = "PandaTV 群组发言"
    chat_name = "PandaTV_Emby_Bot"
    bot_checkin_cmd = "签到"
    skip = 14

    async def send_checkin(self, **kw):
        cmd = random.choice(to_iterable(self.bot_checkin_cmd))
        await self.send(cmd)
        await self.finish(message="群组发言已发送")
