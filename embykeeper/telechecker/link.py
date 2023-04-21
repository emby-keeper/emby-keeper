import asyncio
import io
import random
from typing import Callable, List, Optional, Tuple
import uuid

import tomli
from loguru import logger
from pyrogram import Client, filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from rich.text import Text


class Link:
    bot = "embykeeper_auth_bot"

    def __init__(self, client: Client):
        self.client = client
        self.log = logger.bind(scheme="telelink", username=client.me.name)

    @property
    def instance(self):
        rd = random.Random()
        rd.seed(uuid.getnode())
        return uuid.UUID(int=rd.getrandbits(128))

    @staticmethod
    async def delete_messages(messages: List[Message]):
        async def delete(m: Message):
            try:
                await m.delete(revoke=True)
            except asyncio.CancelledError:
                pass

        return await asyncio.gather(*[delete(m) for m in messages])

    async def post(
        self, cmd, condition: Callable = None, timeout: int = 10, name: str = None
    ) -> Tuple[Optional[str], Optional[str]]:
        results = {}
        ok = asyncio.Event()
        handler = self.get_handler(cmd, results, ok, condition)
        handler = MessageHandler(handler, filters.text & filters.bot & filters.user(self.bot))
        self.client.add_handler(handler)
        messages = []
        messages.append(await self.client.send_message(self.bot, f"/start quiet"))
        await asyncio.sleep(0.5)
        messages.append(await self.client.send_message(self.bot, cmd))
        try:
            await asyncio.wait_for(ok.wait(), timeout=timeout)
        except asyncio.CancelledError:
            try:
                await asyncio.wait_for(self.delete_messages(messages), 1.0)
            except asyncio.TimeoutError:
                pass
            finally:
                raise
        except asyncio.TimeoutError:
            await self.delete_messages(messages)
            self.log.warning(f"{name}超时.")
            return None
        else:
            await self.delete_messages(messages)
            status, errmsg = [results.get(p, None) for p in ("status", "errmsg")]
            if status == "error":
                self.log.warning(f"{name}错误: {errmsg}.")
                return None
            elif status == "ok":
                return results
            else:
                self.log.warning(f"{name}出现未知错误.")
                return None
        finally:
            self.client.remove_handler(handler)

    @staticmethod
    def get_handler(cmd, results, ok, condition=None):
        async def _handler(client: Client, message: Message):
            try:
                toml = tomli.loads(message.text)
            except tomli.TOMLDecodeError:
                await message.delete(revoke=False)
                return
            else:
                try:
                    if toml.get("command", None) == cmd:
                        if condition is None:
                            cond = True
                        elif asyncio.iscoroutinefunction(condition):
                            cond = await condition(toml)
                        elif callable(condition):
                            cond = condition(toml)
                        if cond:
                            results.update(toml)
                            ok.set()
                            await asyncio.sleep(0.5)
                            await message.delete(revoke=False)
                            return
                except asyncio.CancelledError:
                    try:
                        await asyncio.wait_for(message.delete(revoke=False), 1.0)
                    except asyncio.TimeoutError:
                        pass
                    finally:
                        raise
                else:
                    message.continue_propagation()

        return _handler

    async def auth(self, service: str):
        results = await self.post(f"/auth {service} {self.instance}", name=f"服务 {service.capitalize()} 认证")
        return bool(results)

    async def captcha(self):
        results = await self.post(f"/captcha {self.instance}", timeout=240, name="请求跳过验证码")
        if results:
            return [results.get(p, None) for p in ("token", "proxy", "useragent")]
        else:
            return None, None, None

    async def answer(self, question: str):
        results = await self.post(f"/answer {self.instance} {question}", timeout=60, name="请求问题回答")
        if results:
            return results.get("answer", None)

    async def sendlog(self, message):
        results = await self.post(f"/log {self.instance} {message}", name="发送日志到 Telegram ")
        return bool(results)


class TelegramStream(io.TextIOWrapper):
    def __init__(self, link: Link = None):
        super().__init__(io.BytesIO(), line_buffering=True)
        self.link = link

    def write(self, message):
        message = Text.from_markup(message).plain
        if message.endswith("\n"):
            message = message[:-1]
        if message:
            asyncio.create_task(self.link.sendlog(message))
        super().write(message + "\n")
