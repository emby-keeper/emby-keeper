import asyncio
import random
import string

from pyrogram.types import Message

from embykeeper.ocr import OCRService
from embykeeper.utils import async_partial, nonblocking

from ..lock import misty_locks
from . import Monitor

misty_monitor_pool = {}


class MistyMonitor(Monitor):
    ocr = "digit5-large@v1"
    ocr_lock = asyncio.Lock()

    name = "Misty"
    chat_name = "FreeEmbyGroup"
    chat_keyword = r"空余名额数: (?!0$)"
    bot_username = "EmbyMistyBot"
    notify_create_name = True
    additional_auth = ["prime"]

    async def init(self, initial=True, force_lock=True):
        misty_monitor_pool[self.client.me.id] = self
        self.captcha = None
        self.log.info(f"正在初始化机器人状态.")
        wr = async_partial(self.client.wait_reply, self.bot_username)
        misty_locks.setdefault(self.client.me.id, asyncio.Lock())
        lock = misty_locks.get(self.client.me.id, None)
        if not force_lock:
            lock = nonblocking(lock)
        async with lock:
            for _ in range(20 if initial else 3):
                try:
                    msg: Message = await wr("/cancel")
                    if "选择您要使用的功能" in (msg.caption or msg.text):
                        await asyncio.sleep(random.uniform(2, 4))
                        msg = await wr("⚡️账号功能")
                    if "请选择功能" in (msg.text or msg.caption):
                        await asyncio.sleep(random.uniform(2, 4))
                        msg = await wr("⚡️注册账号")
                        if "请输入验证码" in (msg.caption or msg.text):
                            data = await self.client.download_media(msg, in_memory=True)
                            ocr = await OCRService.get(self.ocr)
                            try:
                                with ocr:
                                    ocr_text = await ocr.run(data)
                            except asyncio.TimeoutError:
                                self.log.info(f"机器人状态初始化失败, 正在重试.")
                                continue
                            self.captcha = ocr_text.translate(
                                str.maketrans("", "", string.punctuation)
                            ).replace(" ", "")
                            self.log.debug(f"接收到验证码: {self.captcha}")
                except (asyncio.TimeoutError, TypeError):
                    continue
                else:
                    if self.captcha and len(self.captcha) == 5:
                        self.log.info(
                            f"机器人状态初始化完成, 当接收到邀请码时将输入验证码 {self.captcha} 以抢注, 请勿操作 @EmbyMistyBot."
                        )
                        return True
                    else:
                        self.log.info(f"机器人状态初始化失败, 正在重试.")
            else:
                self.log.bind(log=True).warning(f"Misty 机器人状态初始化失败, 监控将停止.")
                return False

    async def on_trigger(self, message: Message, key, reply):
        wr = async_partial(self.client.wait_reply, self.bot_username)
        misty_locks.setdefault(self.client.me.id, asyncio.Lock())
        lock = misty_locks.get(self.client.me.id, None)
        async with lock:
            for _ in range(3):
                try:
                    msg = await wr(self.captcha)
                    if "验证码错误" in msg.text:
                        self.log.info(f"验证码错误, 将重新初始化.")
                        if not await self.init(force_lock=False):
                            self.failed.set()
                    elif "暂时停止注册" in msg.text:
                        self.log.info(f"注册名额已满, 将重新初始化并继续监控.")
                        if not await self.init(force_lock=False):
                            self.failed.set()
                        return
                    elif "用户名" in msg.text:
                        msg = await wr(self.unique_name)
                        if "密码" in msg.text:
                            await self.client.send_message(self.bot_username, "/cancel")
                            self.log.bind(msg=True).info(
                                f'已向 Bot @{self.bot_username} 发送了用户注册申请: "{self.unique_name}", 请检查结果.'
                            )
                except asyncio.TimeoutError:
                    pass
            else:
                self.log.info(f"未成功, 结束注册申请.")
