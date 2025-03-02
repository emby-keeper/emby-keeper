import random
import string
from loguru import logger

from embykeeper.config import config

logger = logger.bind(scheme="cfsolver")


async def get_cf_clearance(url: str, proxy: str = None):
    from embykeeper.telegram.link import Link
    from embykeeper.telegram.session import ClientsSession
    from embykeeper.wssocks import WSSocks

    telegrams = config.telegram.account
    if not len(telegrams):
        logger.warning(f"未设置 Telegram 账号, 无法使用验证码解析.")
    async with ClientsSession(telegrams[:1]) as clients:
        async for _, tg in clients:
            for i in range(3):
                ws_url, token = await Link(tg).wssocks()
                if not token:
                    logger.warning(f"反向代理服务器申请失败, 正在重试 ({i+1}/3).")
                    continue
                wssocks = WSSocks(proxy=proxy)
                try:
                    connector_token = "".join(random.choices(string.ascii_letters + string.digits, k=16))
                    output = await wssocks.start(ws_url, token, connector_token, proxy)
                    if output:
                        logger.warning(f"连接到反向代理服务器失败, 正在重试 ({i+1}/3)")
                        logger.debug(f"WSSocks 输出:\n{output}")
                        continue
                    cf_clearance, useragent = await Link(tg).captcha_wssocks(connector_token, url)
                    if not cf_clearance:
                        logger.warning(f"解析失败, 正在重试 ({i+1}/3).")
                        continue
                    return cf_clearance, useragent
                finally:
                    wssocks.stop()
            else:
                return None, None
