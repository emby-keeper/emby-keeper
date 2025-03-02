import asyncio
from datetime import datetime, timedelta
import random
import re
from urllib.parse import parse_qs, urlparse

from pyrogram.types import Message
from pyrogram.raw.functions.messages import RequestWebView
from pyrogram.errors import MessageIdInvalid
from faker import Faker
import httpx

from embykeeper.config import config
from embykeeper.utils import show_exception, truncate_str, get_proxy_str

from ..link import Link
from . import BotCheckin


class FutureCheckin(BotCheckin):
    name = "未响"
    bot_username = "lotayu_bot"
    bot_use_captcha = False
    bot_checkin_cmd = "/start"
    bot_text_ignore = ["請先完成驗證"]
    bot_fail_keywords = ["不能签到"]
    additional_auth = ["captcha"]
    max_retries = 2

    click_button = ["签到", "簽到"]

    async def send_checkin(self, retry=False):
        """发送签到命令, 或依次发送签到命令序列."""
        history_message = await self.get_history_message(limit=10)
        if history_message:
            await self.message_handler(self.client, history_message)
            return
        return await super().send_checkin(retry=retry)

    async def get_history_message(self, limit=0):
        """处理 limit 条历史消息, 并检测是否有验证."""
        try:
            m: Message
            async for m in self.client.get_chat_history(self.chat_name or self.bot_username, limit=limit):
                if m.text and "點擊下方按鈕並驗證您的身份" in m.text:
                    time_match = re.search(r"當前時間:(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", m.text)
                    if not time_match:
                        return None
                    time_str = time_match.group(1)
                    current_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    now = datetime.now()
                    time_difference = now - current_time
                    if time_difference <= timedelta(minutes=2):
                        return m
                    else:
                        return None
                elif m.caption and "您的驗證已經通過" in m.caption:
                    return None
        except Exception as e:
            self.log.warning("读取历史消息失败, 将不再读取历史消息.")
            show_exception(e)
            return None

    async def message_handler(self, client, message: Message):
        if message.text and "未加入" in message.text:
            self.log.warning(f"签到失败: 账户错误.")
            return await self.fail()

        if message.text and "您有一個還在進行中的驗證會話" in message.text:
            self.log.warning(f"签到失败: 验证码解析异常, 之前有未完成的验证.")
            return await self.fail()

        if message.text and "驗證您的身份" in message.text and message.reply_markup:
            keys = [b for r in message.reply_markup.inline_keyboard for b in r]
            for b in keys:
                if "Verify" in b.text and b.web_app:
                    url = b.web_app.url
                    bot_peer = await self.client.resolve_peer(self.bot_username)
                    url_auth = (
                        await self.client.invoke(
                            RequestWebView(peer=bot_peer, bot=bot_peer, platform="ios", url=url)
                        )
                    ).url
                    if not await self.solve_captcha(url_auth):
                        self.log.warning("签到失败: 验证码解析失败, 正在重试.")
                        await asyncio.sleep(self.bot_retry_wait)
                        await self.retry()
                        return
                    else:
                        await asyncio.sleep(random.uniform(3, 5))
                        self.log.info("已成功验证, 即将重新进行签到流程.")
                        return
            else:
                self.log.warning(f"签到失败: 账户错误.")
                return await self.fail()

        if (
            message.caption
            and ("開始回響" in message.caption or "開始操作" in message.caption)
            and message.reply_markup
        ):
            keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if any([i in k for i in self.click_button]):
                    try:
                        await message.click(k)
                    except (MessageIdInvalid, TimeoutError):
                        pass
                    return
            else:
                self.log.warning(f"签到失败: 账户错误.")
                return await self.fail()
        await super().message_handler(client, message)

    async def solve_captcha(self, url: str):
        token = await Link(self.client).captcha("future_echo")
        if not token:
            return False
        else:
            scheme = urlparse(url)
            params = parse_qs(scheme.query)
            url_submit = scheme._replace(path="/x/api/submit", query="", fragment="").geturl()
            uuid = params.get("id", [None])[0]
            origin = scheme._replace(path="/", query="", fragment="").geturl()
            useragent = Faker().safari()
            headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": url,
                "Origin": origin,
                "User-Agent": useragent,
            }
            data = {
                "uuid": uuid,
                "cf-turnstile-response": token,
            }
            for i in range(10):
                try:
                    async with httpx.AsyncClient(http2=True, proxy=get_proxy_str(config.proxy)) as client:
                        resp = await client.post(url_submit, headers=headers, data=data)
                        result = resp.text
                        if "完成" in result:
                            return True
                        else:
                            self.log.warning(
                                f"验证码识别后接口返回异常信息:\n{truncate_str(result, 100)}, 可能是您的请求 IP 风控等级较高导致的."
                            )
                            return False
                except (httpx.ProxyError, httpx.TimeoutException, OSError):
                    self.log.warning(
                        f"无法连接到站点的页面, 可能是您的网络或代理不稳定, 正在重试 ({i+1}/10)."
                    )
                    continue
            else:
                self.log.warning(f'无法连接到站点的页面: "{url_submit}", 可能是您的网络或代理不稳定.')
                return False
