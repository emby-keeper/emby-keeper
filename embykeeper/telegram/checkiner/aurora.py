from json import JSONDecodeError
from urllib.parse import parse_qs, urlparse

from curl_cffi.requests import AsyncSession, RequestsError, Response
from pyrogram.raw.functions.users import GetFullUser
from pyrogram.raw.functions.messages import RequestWebView

from embykeeper.runinfo import RunStatus
from embykeeper.utils import get_proxy_str, show_exception
from embykeeper.config import config

from . import BotCheckin


class AuroraCheckin(BotCheckin):
    name = "Aurora Media"
    bot_username = "AuroraMedia1_bot"
    max_retries = 1
    additional_auth = ["prime"]

    async def send_checkin(self, **kw):
        bot_peer = await self.client.resolve_peer(self.bot_username)
        user_full = await self.client.invoke(GetFullUser(id=bot_peer))
        url = user_full.full_user.bot_info.menu_button.url
        url_auth = (
            await self.client.invoke(RequestWebView(peer=bot_peer, bot=bot_peer, platform="ios", url=url))
        ).url

        scheme = urlparse(url_auth)
        params = parse_qs(scheme.fragment)
        webapp_data = params.get("tgWebAppData", [""])[0]

        # 新的API端点
        base_url = "https://server.auroramedia.me"
        url_login = f"{base_url}/aurora/v1/user/login"
        url_checkin = f"{base_url}/aurora/v1/user/checkin"

        try:
            async with AsyncSession(
                proxy=get_proxy_str(config.proxy), impersonate="edge", allow_redirects=True
            ) as session:
                # 登录获取token
                headers = {"Authorization": f"tma {webapp_data}"}
                resp_login: Response = await session.post(url_login, headers=headers)
                login_results = resp_login.json()

                if login_results.get("code") != 200:
                    self.log.info("登录失败: 账户错误.")
                    return await self.fail(message="账户错误")

                token = login_results["data"]["token"]

                # 使用token进行签到
                headers = {"Authorization": f"Bearer-{token}"}
                resp = await session.get(url_checkin, headers=headers)
                results = resp.json()

                code = results.get("code")
                message = results.get("message")
                if "已经签到过了" in message:
                    self.log.info(f"今日已经签到过了.")
                    return await self.finish(RunStatus.NONEED, "今日已签到")
                if code != 200:
                    self.log.info(f"签到失败, 请求状态为 {code}: {message}.")
                    return await self.retry()

                points = results["data"]["points"]
                add_points = results["data"]["addPoints"]
                self.log.info(f"[yellow]签到成功[/]: + {add_points} 分 -> {points} 分.")
                return await self.finish(RunStatus.SUCCESS, "签到成功")

        except (RequestsError, OSError, JSONDecodeError) as e:
            self.log.info(f"签到失败: 无法连接签到页面 ({e.__class__.__name__}).")
            show_exception(e)
            return await self.retry()
