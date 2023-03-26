from pathlib import Path

import toml
import typer
import uvloop
from loguru import logger
from rich import print, traceback
from rich.logging import Console, RichHandler

uvloop.install()
traceback.install()

from . import __author__, __name__, __url__, __version__
from .settings import check_config, get_faked_config
from .utils import Flagged, FlagValueCommand, to_iterable


def _formatter(record):
    extra = record["extra"]
    scheme = extra.get("scheme", None)

    def ifextra(keys, pattern="{}"):
        keys = to_iterable(keys)
        if all(k in extra for k in keys):
            return pattern.format(*[f"{{extra[{k}]}}" for k in keys])
        else:
            return ""

    if scheme in ("telegram", "telechecker", "telemonitor", "telemessager"):
        username = ifextra("username", " ([cyan]{}[/])")
        name = ifextra("name", "([magenta]{}[/]) ")
        return f"[blue]{scheme.capitalize()}[/]{username}: {name}{{message}}"
    elif scheme == "embywatcher":
        ident = ifextra(["server", "username"], " ([cyan]{}:{}[/])")
        return f"[blue]Embywatcher[/]{ident}: {{message}}"
    else:
        return "{message}"


logger.remove()
logger.add(RichHandler(console=Console(stderr=True), markup=True, rich_tracebacks=True), format=_formatter)


def prepare_config(config=None):
    if not config:
        logger.warning("需要输入一个toml格式的config文件.")
        default_config = "config.toml"
        if not Path(default_config).exists():
            with open(default_config, "w+") as f:
                toml.dump(get_faked_config(), f)
                logger.warning(f'您可以根据生成的参考配置文件"{default_config}"进行配置')
        return
    with open(config) as f:
        config = toml.load(f)
    if not check_config(config):
        return
    proxy = config.get("proxy", None)
    if proxy:
        proxy.setdefault("scheme", "socks5")
        proxy.setdefault("host", "127.0.0.1")
        proxy.setdefault("port", "1080")
    return config


app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def version(version):
    if version:
        print(__version__)
        raise typer.Exit()


@app.command(
    cls=FlagValueCommand, help=f"欢迎使用 [orange3]{__name__.capitalize()}[/] {__version__} :cinema: 无参数默认开启全部功能."
)
def main(
    config: Path = typer.Argument(
        None,
        envvar=f"{__name__.upper()}_CONFIG",
        dir_okay=False,
        allow_dash=True,
        rich_help_panel="参数",
        help="配置文件 (置空以生成)",
    ),
    checkin: str = typer.Option(
        Flagged("", "6:00PM"),
        "--checkin",
        "-c",
        rich_help_panel="Telegram 参数",
        show_default="不指定值时默认为6:00PM",
        help="启用每日指定时间签到",
    ),
    monitor: bool = typer.Option(False, "--monitor", "-m", rich_help_panel="Telegram 参数", help="启用群聊监视"),
    send: bool = typer.Option(False, "--send", "-s", rich_help_panel="Telegram 参数", help="启用自动水群"),
    emby: int = typer.Option(
        Flagged(0, 7), "--emby", "-e", min=0, rich_help_panel="Emby 参数", help="启用Emby自动登录"
    ),
    instant: bool = typer.Option(
        True, "--instant/--no-instant", "-i/-I", rich_help_panel="调试 参数", help="立刻执行一次计划任务"
    ),
    debug: bool = typer.Option(False, "--debug", "-d", rich_help_panel="调试 参数", help="开启调试模式, 错误将会导致程序停止运行"),
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        rich_help_panel="调试 参数",
        callback=version,
        is_eager=True,
        help=f"打印{__name__}版本",
    ),
    follow: bool = typer.Option(False, "--follow", "-f", rich_help_panel="调试 参数", help="仅启动消息调试"),
    analyze: bool = typer.Option(False, "--analyze", "-a", rich_help_panel="调试 参数", help="仅启动历史信息分析"),
):
    config = prepare_config(config)
    if not config:
        raise typer.Exit()
    if debug:
        config.setdefault("nofail", False)
        logger.warning("您当前处于调试模式, 错误将会导致程序停止运行.")
    if not checkin and not monitor and not emby and not send:
        checkin = "08:00"
        emby = 7
        monitor = True
        send = True

    logger.info(f"欢迎使用 [orange3]{__name__.capitalize()}[/]! 正在启动, 请稍等. 您可以通过 Ctrl+C 以结束运行.")
    logger.info(f'当前版本 ({__version__}) 活跃贡献者: {", ".join(__author__)}.')

    import asyncio
    from datetime import datetime

    import schedule
    from dateutil import parser

    from .embywatcher.main import watcher
    from .telechecker.main import analyzer, checkiner, follower, messager, monitorer

    if follow:
        return asyncio.run(follower(config))
    if analyze:
        indent = " " * 29
        chats = typer.prompt(indent + "请输入群组用户名 (以空格分隔)").split()
        keywords = typer.prompt(indent + "请输入关键词 (以空格分隔)", default="", show_default=False)
        keywords = keywords.split() if keywords else []
        timerange = typer.prompt(indent + '请输入时间范围 (以"-"分割)', default="", show_default=False)
        timerange = timerange.split("-") if timerange else []
        limit = typer.prompt(indent + "请输入各群组最大获取数量", default=1000, type=int)
        return asyncio.run(analyzer(config, chats, keywords, timerange, limit))

    loop = asyncio.new_event_loop()

    def stop_loop():
        try:
            tasks = asyncio.all_tasks(loop)
            for t in tasks:
                t.cancel()
            loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
        finally:
            asyncio.set_event_loop(None)
            loop.close()

    def exception_handler(l, context):
        e: Exception = context.get("exception")
        logger.opt(exception=e).error(
            f'发生错误, {__name__.capitalize()} 将退出, 请在 "{__url__}/issues/new" 提供反馈以帮助作者修复该问题:'
        )
        loop.stop()

    def run_coros(coros):
        return loop.run_until_complete(asyncio.gather(*coros))

    def run_pending_async(scheduler):
        async def wrapper():
            while True:
                scheduler.run_pending()
                await asyncio.sleep(1)

        return wrapper()

    loop.set_exception_handler(exception_handler)
    asyncio.set_event_loop(loop)

    if instant:
        instants = []
        if emby:
            instants.append(watcher(config))
        if checkin:
            instants.append(checkiner(config, instant=True))
        run_coros(instants)

    if emby:
        schedule_emby = schedule.Scheduler()
        loop.create_task(run_pending_async(schedule_emby))
        schedule_emby.every(emby).days.at(datetime.now().strftime("%H:%M:%S")).do(
            lambda: loop.create_task(watcher(config))
        )
        logger.bind(scheme="embywatcher").info(
            f"下一次保活将在 {schedule_emby.next_run.strftime('%m-%d %H:%M %p')} 进行."
        )
    if checkin:
        schedule_checkin = schedule.Scheduler()
        loop.create_task(run_pending_async(schedule_checkin))
        checkin = parser.parse(checkin).time().strftime("%H:%M:%S")
        schedule_checkin.every().day.at(checkin).do(lambda: loop.create_task(checkiner(config)))
        logger.bind(scheme="telechecker").info(
            f"下一次签到将在 {schedule_checkin.next_run.strftime('%m-%d %H:%M %p')} 进行."
        )
    if send:
        schedule_send = schedule.Scheduler()
        loop.create_task(run_pending_async(schedule_send))
        messager(config, loop, schedule_send)
    if monitor:
        loop.create_task(monitorer(config))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        print("\r"),
    finally:
        stop_loop()
        logger.info("所有客户端已停止, 欢迎您再次使用 Embykeeper.")


if __name__ == "__main__":
    app()
