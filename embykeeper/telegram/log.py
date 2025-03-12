import asyncio
import io

from rich.text import Text
from loguru import logger

from embykeeper.schema import TelegramAccount
from embykeeper.utils import show_exception

from .link import Link
from .session import ClientsSession

logger = logger.bind(scheme="telenotifier")


class TelegramStream(io.TextIOWrapper):
    """消息推送处理器类"""

    def __init__(self, account: TelegramAccount, instant=False):
        super().__init__(io.BytesIO(), line_buffering=True)
        self.account = account
        self.instant = instant

        self.queue = asyncio.Queue()
        self.watch = asyncio.create_task(self.watchdog())

    async def watchdog(self):
        while True:
            message = await self.queue.get()
            try:
                result = await asyncio.wait_for(self.send(message), 20)
            except asyncio.TimeoutError:
                logger.warning("推送消息到 Telegram 超时.")
            except Exception as e:
                logger.warning("推送消息到 Telegram 失败.")
                show_exception(e)
            else:
                if not result:
                    logger.warning(f"推送消息到 Telegram 失败.")
            finally:
                self.queue.task_done()

    async def send(self, message):
        async with ClientsSession([self.account]) as clients:
            async for _, tg in clients:
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
