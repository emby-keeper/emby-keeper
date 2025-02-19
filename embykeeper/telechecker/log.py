import asyncio
import io

from rich.text import Text
from loguru import logger

from .link import Link
from .tele import ClientsSession

logger = logger.bind(scheme="telenotifier")

from asyncio import constants

constants.LOG_THRESHOLD_FOR_CONNLOST_WRITES = 1000000


class TelegramStream(io.TextIOWrapper):
    """消息推送处理器类"""

    def __init__(self, account, proxy=None, basedir=None, instant=False):
        super().__init__(io.BytesIO(), line_buffering=True)
        self.account = account
        self.proxy = proxy
        self.basedir = basedir
        self.instant = instant

        self.queue = asyncio.Queue()
        self.watch = asyncio.create_task(self.watchdog())

    async def watchdog(self):
        while True:
            message = await self.queue.get()
            try:
                result = await asyncio.wait_for(self.send(message), 10)
            except asyncio.TimeoutError:
                logger.warning("推送消息到 Telegram 超时.")
            else:
                if not result:
                    logger.warning(f'推送消息到 Telegram 失败: 无法登录 {self.account["phone"]}.')
            finally:
                self.queue.task_done()

    async def send(self, message):
        async with ClientsSession([self.account], proxy=self.proxy, basedir=self.basedir) as clients:
            async for tg in clients:
                if self.instant:
                    return await Link(tg).send_msg(message)
                else:
                    return await Link(tg).send_log(message)
            else:
                return False

    def write(self, message):
        message = Text.from_markup(message).plain
        if message.endswith("\n"):
            message = message[:-1]
        if message:
            self.queue.put_nowait(message)

    async def join(self):
        await self.queue.join()
        self.watch.cancel()
