import base64
import os
from typing import List

from loguru import logger
from rich.prompt import Confirm, Prompt, IntPrompt, Confirm

from .config import ConfigManager, config
from .schema import Config, TelegramAccount, EmbyAccount
from .var import console
from .log import pad
from . import __url__


async def convert_session(accounts: List[TelegramAccount]):
    from .telegram.session import ClientsSession

    for a in accounts:
        success = False
        async with ClientsSession([a]) as clients:
            async for a, tg in clients:
                a.session = await tg.export_session_string()
                logger.info(f'账号 "{a.phone}" 登陆成功.')
                success = True
            if not success:
                logger.error(f'账号 "{a.phone}" 登陆失败, 已被禁用.')
                a.enabled = False
    return accounts


async def interactive_config():
    from tomlkit import item

    cfg = Config()
    config.set(cfg)
    pad = " " * 23
    logger.info("我们将为您生成配置, 需要您根据提示填入信息, 并按回车确认.")
    logger.info(f"配置帮助详见: {__url__}.")
    logger.info(f"若需要重新开始, 请点击右上方的刷新按钮.")
    logger.info(f"若您需要更加高级的配置, 请使用右上角的 Config 按钮以修改配置文件.")

    mongodb_url = Prompt.ask(
        pad + "请输入 MongoDB 连接地址 [dark_green](mongodb://user:pass@host:port)[/]", console=console
    )
    cfg.mongodb = mongodb_url

    telegram_accounts = cfg.telegram.account
    while True:
        if len(telegram_accounts) > 0:
            logger.info(
                f"您当前填写了 {len(telegram_accounts)} 个 Telegram 账号信息: "
                f'{", ".join([t.phone for t in telegram_accounts])}'
            )
            more = Confirm.ask(pad + "是否继续添加?", default=False, console=console)
        else:
            more = Confirm.ask(pad + "是否添加 Telegram 账号?", default=True, console=console)
        if not more:
            break
        phone = Prompt.ask(
            pad + "请输入您的 Telegram 账号 (带国家区号) [dark_green](+861xxxxxxxxxx)[/]",
            console=console,
        )
        monitor = Confirm.ask(
            pad + "是否开启该账号的自动监控功能? (需要高级账号)", default=False, console=console
        )
        messager = Confirm.ask(
            pad + "是否开启该账号的自动水群功能? (需要高级账号)", default=False, console=console
        )
        telegram_accounts.append(TelegramAccount(phone=phone, monitor=monitor, messager=messager))
    if telegram_accounts:
        logger.info(f"即将尝试登录各账户并存储凭据, 请耐心等待.")
        await convert_session(telegram_accounts)

    emby_accounts = cfg.emby.account
    while True:
        if len(emby_accounts) > 0:
            logger.info(f"您当前填写了 {len(emby_accounts)} 个 Emby 账号信息.")
            more = Confirm.ask(pad + "是否继续添加?", default=False, console=console)
        else:
            more = Confirm.ask(pad + "是否添加 Emby 账号?", default=True, console=console)
        if not more:
            break
        url = Prompt.ask(
            pad + "请输入您的 Emby 站点 URL [dark_green](https://abc.com:443)[/]", console=console
        )
        username = Prompt.ask(pad + "请输入您在该 Emby 站点的用户名", console=console)
        password = Prompt.ask(
            pad + "请输入您在该 Emby 站点的密码 (不显示, 按回车确认)",
            password=True,
            console=console,
        )
        while True:
            time = Prompt.ask(
                pad + "设置模拟观看时长范围 (秒), 用空格分隔",
                default="120 240",
                show_default=True,
                console=console,
            )
            if " " in time:
                try:
                    time = [int(t) for t in time.split(None, 1)]
                    break
                except ValueError:
                    logger.warning(f"时长设置不正确, 请重新输入.")
            else:
                try:
                    time = int(time)
                    break
                except ValueError:
                    logger.warning(f"时长设置不正确, 请重新输入.")
        emby_accounts.append(EmbyAccount(url=url, username=username, password=password, time=time))
    advanced = Confirm.ask(pad + "是否配置高级设置", default=False, console=console)
    if advanced:
        while True:
            logger.info("发送关键日志消息到以下哪个账户?")
            logger.info(f"\t0. 不使用消息推送功能")
            for i, t in enumerate(telegram_accounts):
                logger.info(f'\t{i+1}. {t["phone"]}')
            selected = IntPrompt.ask(pad + "请选择", default=1, console=console)
            if selected:
                if selected > 0:
                    if selected <= len(telegram_accounts):
                        cfg.notifier.enabled = True
                        cfg.notifier.account = selected
                        break
                    else:
                        logger.warning("选择的账号不存在, 请重新选择.")
                else:
                    cfg.notifier.enabled = False
                    break
            else:
                logger.warning("选择的账号不存在, 请重新选择.")
        cfg.checkiner.timeout = IntPrompt.ask(
            pad + "设置每个 Telegram Bot 签到的最大尝试时间 (秒)",
            default=cfg.checkiner.timeout,
            show_default=True,
            console=console,
        )
        cfg.checkiner.retries = IntPrompt.ask(
            pad + "设置每个 Telegram Bot 签到的最大尝试次数",
            default=cfg.checkiner.retries,
            show_default=True,
            console=console,
        )
        cfg.checkiner.concurrency = IntPrompt.ask(
            pad + "设置最大可同时进行的 Telegram Bot 签到",
            default=cfg.checkiner.concurrency,
            show_default=True,
            console=console,
        )
        cfg.checkiner.random_start = IntPrompt.ask(
            pad + "设置计划任务时, 各站点之间签到的随机时间差异 (分钟)",
            default=cfg.checkiner.random_start,
            show_default=True,
            console=console,
        )
    content = item(cfg.model_dump(exclude_none=True)).as_string().encode()
    content = base64.b64encode(content)
    logger.info(
        f"您的配置[green]已生成完毕[/]! 您需要将以下内容写入托管平台的 EK_CONFIG 环境变量 ([red]SECRET[/]), 否则配置将在重启后丢失."
    )
    console.print()
    console.rule("EK_CONFIG")
    console.print(content.decode())
    console.rule()
    console.print()
    start_now = Confirm.ask(pad + "是否立即启动?", default=True, console=console)
    if start_now:
        config.set(cfg)
        return True
    else:
        return False


async def prepare_config(env_config: str):
    from tomlkit import item

    cfg = ConfigManager.load_env_config(env_config)
    cfg = ConfigManager.validate_config(cfg)
    config.set(cfg)
    if not cfg:
        return False

    # Add MongoDB check
    if not cfg.mongodb:
        logger.warning("未设置 MongoDB 连接, 所有缓存数据将在重启后遗失或重置.")

    to_login = []
    for a in cfg.telegram.account:
        if not a.session:
            to_login.append(a)
    if to_login:
        logger.info("即将尝试登陆各个账号.")
        await convert_session(to_login)
        content = item(cfg.model_dump(exclude_none=True)).as_string().encode()
        content = base64.b64encode(content)
        logger.info(
            f"您已登陆到 Telegram! 您需要将以下内容重新写入托管平台的 EK_CONFIG 环境变量 ([red]SECRET[/]), "
            "否则登陆状态将在重启后丢失."
        )
        console.print()
        console.rule("EK_CONFIG")
        console.print(content.decode())
        console.rule()
        console.print()
        start_now = Confirm.ask(pad + "是否立即启动?", default=True, console=console)
        if start_now:
            config.set(cfg)
            return True
        else:
            return False
    else:
        return True


async def public_entrypoint():
    env_config = os.environ.get(f"EK_CONFIG", None)
    if env_config:
        return await prepare_config(env_config)
    else:
        return await interactive_config()
