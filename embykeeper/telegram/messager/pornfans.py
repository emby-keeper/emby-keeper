import asyncio
from datetime import datetime, time

from ..lock import (
    pornfans_nohp,
    pornfans_messager_enabled,
    pornfans_messager_mids,
    pornfans_messager_mids_lock,
    pornfans_alert,
)
from . import Messager

__ignore__ = True


class PornfansMessager(Messager):
    name = "PornFans"
    chat_name = "embytestflight"
    default_messages = ["pornfans-common-wl@latest.yaml * 100"]

    async def init(self):
        self.lock = asyncio.Lock()
        pornfans_messager_enabled[self.me.id] = True
        async with pornfans_messager_mids_lock:
            if self.me.id not in pornfans_messager_mids:
                pornfans_messager_mids[self.me.id] = []
        return True

    async def send(self, message):
        if pornfans_alert.get(self.me.id, False):
            self.log.info(f"由于风险急停取消发送.")
            return
        nohp_date = pornfans_nohp.get(self.me.id, None)
        if nohp_date and nohp_date >= datetime.today().date():
            self.log.info(f"取消发送: 血量已耗尽.")
            return
        msg = await super().send(message)
        if msg:
            pornfans_messager_mids[self.me.id].append(msg.id)
        return msg
