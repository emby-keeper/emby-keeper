import asyncio
import random
from urllib.parse import parse_qs, urlparse

from pyrogram import filters
from pyrogram.types import Message
from pyrogram.raw.functions.messages import RequestWebView
from pyrogram.errors import MessageIdInvalid
import httpx
from faker import Faker

from embykeeper.config import config
from embykeeper.utils import get_proxy_str

from ..link import Link
from . import Monitor


class FutureMonitor(Monitor):
    name = "未响"
    chat_keyword = r"FutureEcho-register-\w{8}-\w{4}-\w{3}-\w{5}"
    bot_username = "lotayu_bot"
    chat_name = "FutureEcho_Chat"
    notify_create_name = True
    allow_edit = False
    additional_auth = ["captcha"]

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
            try:
                async with httpx.AsyncClient(http2=True, proxy=get_proxy_str(config.proxy)) as client:
                    resp = await client.post(url_submit, headers=headers, data=data)
                    result = resp.text
                    if "完成" in result:
                        return True
            except:
                return False

    async def on_trigger(self, message: Message, key, reply):
        for i in range(3):
            if i:
                self.log.info(f"正在重试注册 ({i}/3).")
            msg = await self.client.wait_reply(self.bot_username, f"/start")
            text = msg.text or msg.caption
            if "你还未加入" in text:
                self.log.error("账户错误, 无法注册.")
                return
            async with self.client.catch_reply(self.bot_username) as f1:
                async with self.client.catch_edit(msg, ~filters.regex("请先完成验证")) as f2:
                    try:
                        msg = await msg.click("💡註冊帳戶", timeout=1)
                    except (TimeoutError, MessageIdInvalid):
                        pass
                    except ValueError:
                        self.log.error("未能找到注册按钮, 无法注册.")
                        return
                    try:
                        done, pending = await asyncio.wait(
                            [f1, f2], return_when=asyncio.FIRST_COMPLETED, timeout=10
                        )
                    except asyncio.TimeoutError:
                        self.log.error("点击注册按钮无响应, 无法注册.")
                        return
                    else:
                        for f in pending:
                            f.cancel()
                        msg = list(done)[0].result()
            text = msg.text or msg.caption
            if "验证您的身份" in text:
                self.log.info("需要验证身份, 正在解析.")
                url = None
                if msg.reply_markup:
                    buttons = [button for line in msg.reply_markup.inline_keyboard for button in line]
                    for b in buttons:
                        if "Verify" in b.text and b.web_app:
                            url = b.web_app.url
                            break
                if not url:
                    self.log.error("需要验证身份但没有找到 URL, 无法注册.")
                    return
                bot_peer = await self.client.resolve_peer(self.bot_username)
                url_auth = (
                    await self.client.invoke(
                        RequestWebView(peer=bot_peer, bot=bot_peer, platform="ios", url=url)
                    )
                ).url
                if not await self.solve_captcha(url_auth):
                    self.log.error("验证码解析失败, 无法注册.")
                    return
                else:
                    await asyncio.sleep(random.uniform(3, 5))
                    self.log.info("已成功验证, 重新进行注册流程.")
                    continue
            else:
                if ("邀請碼" in text) or ("邀请码" in text):
                    msg = await self.client.wait_reply(self.bot_username, key)
                    text = msg.text or msg.caption
                    if "无效" in text:
                        self.log.error("邀请码无效, 无法注册.")
                        return
                if "用户名" in text:
                    msg = await self.client.wait_reply(self.bot_username, self.unique_name)
                    text = msg.text or msg.caption
                if "邮箱地址" in text:
                    msg = await self.client.wait_reply(self.bot_username, f"{self.unique_name}@gmail.com")
                    text = msg.text or msg.caption
                if "创建成功" in text:
                    self.log.bind(msg=True).info(f"已在 Bot @{self.bot_username} 成功创建用户, 请查看.")
                    return
                else:
                    self.log.warning(f"注册失败, 可能是注册流程出错, 请检查.")
                    return
