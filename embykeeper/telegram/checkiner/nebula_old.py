import asyncio
from json import JSONDecodeError
from urllib.parse import parse_qs, urlencode, urlparse

import httpx
from pyrogram.raw.functions.messages import RequestWebView
from pyrogram.raw.functions.users import GetFullUser
from faker import Faker

from embykeeper.runinfo import RunStatus
from embykeeper.utils import remove_prefix, get_proxy_str, show_exception
from embykeeper.config import config

from ..link import Link
from . import BotCheckin


class NebulaCheckin(BotCheckin):
    name = "Nebula"
    bot_username = "Nebula_Account_bot"
    max_retries = 1

    async def send_checkin(self, **kw):
        bot_peer = await self.client.resolve_peer(self.bot_username)
        user_full = await self.client.invoke(GetFullUser(id=bot_peer))
        url = user_full.full_user.bot_info.menu_button.url
        url_auth = (
            await self.client.invoke(RequestWebView(peer=bot_peer, bot=bot_peer, platform="ios", url=url))
        ).url
        self.log.debug(f"请求面板: {url_auth}")
        scheme = urlparse(url_auth)
        data = remove_prefix(scheme.fragment, "tgWebAppData=")
        url_base = scheme._replace(path="/api/proxy/userCheckIn", query=f"data={data}", fragment="").geturl()
        scheme = urlparse(url_base)
        query = parse_qs(scheme.query, keep_blank_values=True)
        query = {k: v for k, v in query.items() if not k.startswith("tgWebApp")}
        token = await Link(self.client).captcha("nebula")
        if not token:
            self.log.warning("签到失败: 无法获得验证码.")
            return await self.fail(message="验证码获取失败")
        useragent = Faker().safari()
        query["token"] = token
        url_checkin = scheme._replace(query=urlencode(query, True)).geturl()
        proxy = get_proxy_str(config.proxy)
        try:
            async with httpx.AsyncClient(http2=True, proxy=proxy) as client:
                resp = await client.get(url_checkin, headers={"User-Agent": useragent})
                results = resp.json()
                message = results["message"]
                if any(s in message for s in ("未找到用户", "权限错误")):
                    self.log.info("签到失败: 账户错误.")
                    return await self.fail(message="账户错误")
                if "失败" in message:
                    self.log.info("签到失败.")
                    return await self.retry()
                if "已经" in message:
                    self.log.info("今日已经签到过了.")
                    return await self.finish(RunStatus.NONEED, "今日已签到")
                elif "成功" in message:
                    self.log.info(
                        f"[yellow]签到成功[/]: + {results['data']['get_credit']} 分 -> {results['data']['credit']} 分."
                    )
                    return await self.finish(RunStatus.SUCCESS, "签到成功")
                else:
                    self.log.warning(f"接收到异常返回信息: {message}")
                    return await self.retry()
        except (httpx.HTTPError, OSError, JSONDecodeError) as e:
            self.log.info(f"签到失败: 无法连接签到页面 ({e.__class__.__name__}).")
            show_exception(e)
            return await self.retry()
