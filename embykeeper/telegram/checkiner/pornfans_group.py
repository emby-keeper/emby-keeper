import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, time
import random

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.enums import MessageEntityType

from embykeeper.runinfo import RunStatus

from ..messager._smart import SmartMessager
from ..lock import pornfans_alert, pornfans_messager_mids_lock, pornfans_messager_mids
from . import BotCheckin

__ignore__ = True


class SmartPornfansCheckinMessager(SmartMessager):
    name = "PornFans 签到群发言"
    chat_name = "PornFans_Chat"
    default_messages = "pornfans-checkin-wl@latest.yaml"
    additional_auth = ["pornfans_pack"]
    msg_per_day = 1
    force_day = True
    at = [time(6, 0), time(23, 59)]
    extra_prompt = "输出内容必须大于 8 个字符, 包括符号"

    async def init(self):
        async with pornfans_messager_mids_lock:
            if self.me.id not in pornfans_messager_mids:
                pornfans_messager_mids[self.me.id] = []
        return True

    async def send(self, dummy=False):
        if pornfans_alert.get(self.me.id, False):
            self.log.info(f"由于风险急停取消发送.")
            return
        message = await super().send(dummy=dummy)
        if message:
            pornfans_messager_mids[self.me.id].append(message)
        return message


class PornfansGroupCheckin(BotCheckin):
    name = "PornFans 主群发言"
    bot_username = "Porn_Emby_Bot"
    chat_name = "PornFans_Chat"
    additional_auth = ["pornfans_pack"]
    bot_use_captcha = False

    @asynccontextmanager
    async def listener(self):
        yield

    async def send_checkin(self):
        async def mention_user_filter(flt, __, m: Message):
            if m.entities:
                for e in m.entities:
                    if e.type == MessageEntityType.TEXT_MENTION:
                        if e.user.id == flt.user_id:
                            return True
            return False

        mention = filters.create(mention_user_filter, user_id=self.client.me.id)

        today_start = datetime.combine(datetime.now().date(), time(0, 0))
        async for m in self.client.search_messages(
            self.chat_name, "签到成功", max_date=today_start, from_user=self.bot_username
        ):
            if await mention(self.client, m):
                self.log.info(f"今日已经签到过了.")
                return await self.finish(RunStatus.NONEED, "今日已签到")

        messager = SmartPornfansCheckinMessager(
            self.client, config={"extra_prompt": "请注意: 回复中必须含有签到两个字, 且长度大于8个字!"}
        )

        for _ in range(10):
            async with self.client.catch_reply(
                self.chat_name, filter=mention & filters.user(self.bot_username)
            ) as f:
                msg = await messager.send()
                if not msg:
                    self.log.info(f"发送失败, 正在重试.")
                    continue
                try:
                    r_msg: Message = await asyncio.wait_for(f, 10)
                except asyncio.TimeoutError:
                    wait = random.uniform(180, 360)
                    self.log.info(f"机器人没有回应, 尝试在 {wait:.0f} 秒后重新签到")
                    await asyncio.sleep(wait)
                    continue
                else:
                    if r_msg.text and "签到成功" in r_msg.text:
                        self.log.info("[yellow]签到成功[/]")
                        return await self.finish()
                finally:
                    try:
                        await msg.delete()
                    except:
                        pass
        else:
            self.log.warning(f"签到失败: 重试超限.")
            return await self.fail()
