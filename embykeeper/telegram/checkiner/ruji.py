from datetime import datetime
from urllib.parse import parse_qs, urlparse
import hmac
import hashlib
import random
import string

from pyrogram.types import Message
from pyrogram.raw.functions.messages import RequestWebView
from faker import Faker
import httpx

from embykeeper.utils import to_iterable, truncate_str
from embykeeper.runinfo import RunStatus

from .. import get_telegram_proxy_str
from ..link import Link
from ._templ_a import TemplateACheckin


class RujiCheckin(TemplateACheckin):
    name = "入机"
    bot_username = "ljembyfukh_bot"
    bot_use_captcha = False
    bot_checkin_cmd = "/start"
    additional_auth = ["captcha"]

    signing_secret = "yNPEhmtaRwxYxk0LABf-pCeU6LlmE3CikoPej-g6xpQ"

    def generate_nonce(self, length=21):
        """Generate a random nonce string of specified length."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=length))

    def generate_signature(self, user_id: int, timestamp: int, nonce: str) -> str:
        """Generate HMAC signature using SHA256."""
        message = f"{user_id}:{timestamp}:{nonce}"
        hmac_obj = hmac.new(self.signing_secret.encode(), message.encode(), hashlib.sha256)
        return hmac_obj.hexdigest()

    async def message_handler(self, client, message: Message):
        text = message.caption or message.text
        if (
            text
            and any(keyword in text for keyword in to_iterable(self.templ_panel_keywords))
            and message.reply_markup
        ):
            keys = [k for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if "签到" in k.text and k.web_app:
                    url = k.web_app.url
                    bot_peer = await self.client.resolve_peer(self.bot_username)
                    url_auth = (
                        await self.client.invoke(
                            RequestWebView(peer=bot_peer, bot=bot_peer, platform="ios", url=url)
                        )
                    ).url
                    scheme = urlparse(url_auth)
                    params = parse_qs(scheme.fragment)
                    webapp_data = params.get("tgWebAppData", [""])[0]
                    token = await Link(self.client).captcha("ruji")
                    if not token:
                        self.log.warning("签到失败: 验证码解析失败, 正在重试.")
                        return await self.retry()
                    scheme = urlparse(url)
                    url_submit = scheme._replace(path="/api/checkin/verify", query="", fragment="").geturl()
                    origin = scheme._replace(path="/", query="", fragment="").geturl()
                    useragent = Faker().safari()

                    headers = {
                        "Content-Type": "application/json",
                        "Referer": url,
                        "Origin": origin,
                        "User-Agent": useragent,
                        "X-Requested-With": "XMLHttpRequest",
                    }

                    timestamp = int(datetime.now().timestamp())
                    nonce = self.generate_nonce()
                    signature = self.generate_signature(self.client.me.id, timestamp, nonce)

                    data = {
                        "user_id": str(self.client.me.id),
                        "token": token,
                        "signature": signature,
                        "timestamp": timestamp,
                        "webapp_data": webapp_data,
                        "nonce": nonce,
                    }
                    for i in range(10):
                        try:
                            async with httpx.AsyncClient(
                                http2=True, proxy=get_telegram_proxy_str()
                            ) as client:
                                resp = await client.post(url_submit, headers=headers, json=data)
                                result = resp.text

                                try:
                                    json_result = resp.json()
                                    if resp.status_code == 200:
                                        message = json_result.get("message", "签到成功")
                                        reward = json_result.get("reward", "")
                                        self.log.info(f"{message} {reward}")
                                        return
                                    elif resp.status_code == 409:
                                        detail = json_result.get("detail", "今日已经签到过了")
                                        self.log.info(detail)
                                        return await self.finish(RunStatus.NONEED, "今日已签到")
                                    else:
                                        detail = json_result.get("detail", "未知错误")
                                        self.log.info(detail)
                                        return await self.finish(RunStatus.ERROR, "签到失败")
                                except:
                                    self.log.warning(
                                        f"签到失败: 验证码识别后接口返回异常信息:\n{truncate_str(result, 100)}, 可能是您的请求 IP 风控等级较高导致的."
                                    )
                                    return await self.fail()

                        except (httpx.ProxyError, httpx.TimeoutException, OSError):
                            self.log.warning(
                                f"无法连接到站点的页面, 可能是您的网络或代理不稳定, 正在重试 ({i+1}/10)."
                            )
                            continue
                    else:
                        self.log.warning(f'无法连接到站点的页面: "{url_submit}", 可能是您的网络或代理不稳定.')
                        return await self.retry()
            else:
                self.log.warning(f"签到失败: 账户错误.")
                return await self.fail()

        if message.text and "请先点击下面加入我们的" in message.text:
            self.log.warning(f"签到失败: 账户错误.")
            return await self.fail()

        await super().message_handler(client, message)
