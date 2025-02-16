from ._base import BotCheckin

__ignore__ = True


class TemplateCHATCheckin(BotCheckin):    
    bot_checkin_cmd = "签到"
    

    async def send_checkin(self, retry=False):
        await super().send_checkin(retry=retry)
        self.finished.set()


def use(**kw):
    return type("TemplatedClass", (TemplateCHATCheckin,), kw)
