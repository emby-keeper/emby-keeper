import asyncio
from datetime import datetime
from ._smart import SmartMessager
from ..lock import (
    pornemby_nohp,
    pornemby_messager_enabled,
    pornemby_messager_mids,
    pornemby_alert,
)

__ignore__ = True


class SmartPornembyMessager(SmartMessager):
    name = "Pornemby"
    chat_name = "pornemby"
    default_messages = "pornemby-common-wl@latest.yaml"
    additional_auth = ["pornemby_pack"]
    msg_per_day = 100

    async def init(self):
        self.lock = asyncio.Lock()
        pornemby_messager_enabled[self.me.id] = True
        pornemby_messager_mids[self.me.id] = []
        return True

    async def send(self, dummy=False):
        if pornemby_alert.get(self.me.id, False):
            self.log.info(f"由于风险急停取消发送.")
            return
        nohp_date = pornemby_nohp.get(self.me.id, None)
        if nohp_date and nohp_date >= datetime.today().date():
            self.log.info(f"取消发送: 血量已耗尽.")
            return
        msg = await super().send(dummy=dummy)
        if msg:
            pornemby_messager_mids[self.me.id].append(msg.id)
        return msg
