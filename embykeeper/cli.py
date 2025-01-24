from pathlib import Path
from datetime import datetime, timedelta
import re
import sys
from typing import List
import json

import typer
import asyncio
from dateutil import parser
from loguru import logger

from . import var, __author__, __name__, __url__, __version__
from .utils import Flagged, FlagValueCommand, AsyncTyper, AsyncTaskPool, show_exception
from .settings import prepare_config

app = AsyncTyper(
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

# 在函数外创建绑定的 logger
logger = logger.bind(scheme="embywatcher")

def version(flag):
    if flag:
        print(__version__)
        raise typer.Exit()


def print_example_config(flag):
    if flag:
        import io

        from .settings import write_faked_config

        file = io.StringIO()
        write_faked_config(file, quiet=True)
        file.seek(0)
        print(file.read())
        raise typer.Exit()


async def should_run_emby(config: dict) -> bool:
    """检查是否应该执行 Emby 保活"""
    timestamp_file = Path(config["basedir"]) / "watcher_schedule_next_timestamp"
    
    if timestamp_file.exists():
        try:
            stored_data = json.loads(timestamp_file.read_text())
            next_time = datetime.fromtimestamp(stored_data["timestamp"])
            
            if next_time > datetime.now():
                logger.info(f"Emby保活: 当前时间早于计划的保活时间 ({next_time.strftime('%m-%d %H:%M %p')}), 跳过本次保活.")
                return False
            
            logger.info(f"Emby保活: 已到达计划的保活时间 ({next_time.strftime('%m-%d %H:%M %p')}), 开始执行保活.")
            return True
            
        except (json.JSONDecodeError, KeyError, OSError) as e:
            logger.debug(f"读取保活时间缓存失败: {e}")
            return True  # 如果读取失败，默认执行保活
    
    logger.info("Emby保活: 未找到时间缓存文件，执行首次保活.")
    return True  # 如果没有缓存文件，默认执行保活


@app.async_command(
    cls=FlagValueCommand,
    help=f"欢迎使用 [orange3]{__name__.capitalize()}[/] {__version__} :cinema: 无参数默认开启全部功能.",
)
async def main(
    config: Path = typer.Argument(
        None,
        dir_okay=False,
        allow_dash=True,
        envvar=f"EK_CONFIG_FILE",
        rich_help_panel="参数",
        help="配置文件 (置空以生成)",
    ),
    checkin: str = typer.Option(
        Flagged("", "-"),
        "--checkin",
        "-c",
        rich_help_panel="模块开关",
        show_default="不指定值时默认为 8:00AM-10:00AM 之间随机时间",
        help="启用每日指定时间签到",
    ),
    emby: str = typer.Option(
        Flagged("", "-"),
        "--emby",
        "-e",
        rich_help_panel="模块开关",
        help="启用每隔天数 Emby 自动保活",
        show_default="不指定值时默认为每3-12天",
    ),
    subsonic: str = typer.Option(
        Flagged("", "-"),
        "--subsonic",
        "-S",
        rich_help_panel="模块开关",
        help="启用每隔天数 Subsonic 自动保活",
        show_default="不指定值时默认为3-12天",
    ),
    monitor: bool = typer.Option(False, "--monitor", "-m", rich_help_panel="模块开关", help="启用群聊监视"),
    send: bool = typer.Option(False, "--send", "-s", rich_help_panel="模块开关", help="启用自动水群"),
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        rich_help_panel="调试参数",
        callback=version,
        is_eager=True,
        help=f"打印 {__name__.capitalize()} 版本",
    ),
    example_config: bool = typer.Option(
        None,
        "--example-config",
        "-E",
        hidden=True,
        callback=print_example_config,
        is_eager=True,
        help=f"输出范例配置文件",
    ),
    instant: bool = typer.Option(
        False,
        "--instant/--no-instant",
        "-i/-I",
        envvar="EK_INSTANT",
        show_envvar=False,
        rich_help_panel="调试参数",
        help="启动时立刻执行一次任务",
    ),
    once: bool = typer.Option(
        False, "--once/--cron", "-o/-O", rich_help_panel="调试参数", help="不等待计划执行"
    ),
    verbosity: int = typer.Option(
        False,
        "--debug",
        "-d",
        count=True,
        envvar="EK_DEBUG",
        show_envvar=False,
        rich_help_panel="调试参数",
        help="开启调试模式",
    ),
    debug_cron: bool = typer.Option(
        False,
        envvar="EK_DEBUG_CRON",
        show_envvar=False,
        help="开启任务调试模式, 在三秒后立刻开始执行计划任务",
    ),
    debug_notify: bool = typer.Option(
        False,
        show_envvar=False,
        help="开启日志调试模式, 发送一条日志记录和即时日志记录后退出",
    ),
    simple_log: bool = typer.Option(
        False, "--simple-log", "-L", rich_help_panel="调试参数", help="简化日志输出格式"
    ),
    disable_color: bool = typer.Option(
        False, "--disable-color", "-C", rich_help_panel="调试参数", help="禁用日志颜色"
    ),
    follow: bool = typer.Option(False, "--follow", "-F", rich_help_panel="调试工具", help="仅启动消息调试"),
    analyze: bool = typer.Option(
        False, "--analyze", "-A", rich_help_panel="调试工具", help="仅启动历史信息分析"
    ),
    dump: List[str] = typer.Option([], "--dump", "-D", rich_help_panel="调试工具", help="仅启动更新日志"),
    top: bool = typer.Option(
        True, "--no-top", "-T", rich_help_panel="调试参数", help="执行过程中显示系统调试状态"
    ),
    play: str = typer.Option(None, "--play-url", "-p", rich_help_panel="调试工具", help="仅模拟观看一个视频"),
    save: bool = typer.Option(
        False, "--save", rich_help_panel="调试参数", help="记录执行过程中的原始更新日志"
    ),
    public: bool = typer.Option(
        False,
        "--public",
        "-P",
        hidden=True,
        rich_help_panel="调试参数",
        help="启用公共仓库部署模式",
    ),
    windows: bool = typer.Option(
        False,
        "--windows",
        "-W",
        hidden=True,
        rich_help_panel="调试参数",
        help="启用 Windows 安装部署模式",
    ),
    basedir: Path = typer.Option(
        None, "--basedir", "-B", rich_help_panel="调试参数", help="设定账号文件和模型文件的位置"
    ),
):
    from .log import logger, initialize

    var.debug = verbosity
    if verbosity >= 3:
        level = 0
    elif verbosity >= 1:
        level = "DEBUG"
    else:
        level = "INFO"

    initialize(level=level, show_path=verbosity and (not simple_log), show_time=not simple_log)
    if disable_color:
        var.console.no_color = True

    msg = " 您可以通过 Ctrl+C 以结束运行." if not public else ""
    logger.info(f"欢迎使用 [orange3]{__name__.capitalize()}[/]! 正在启动, 请稍等.{msg}")
    logger.info(f"当前版本 ({__version__}) 项目页: {__url__}")
    logger.debug(f'命令行参数: "{" ".join(sys.argv[1:])}".')

    if verbosity:
        logger.warning(f"您当前处于调试模式: 日志等级 {verbosity}.")
        app.pretty_exceptions_enable = True

    config: dict = await prepare_config(config, basedir=basedir, public=public, windows=windows)

    if verbosity >= 2:
        config["nofail"] = False
    if not config.get("nofail", True):
        logger.warning(f"您当前处于调试模式: 错误将会导致程序停止运行.")
    if debug_cron:
        logger.warning("您当前处于计划任务调试模式, 将在 10 秒后运行计划任务.")

    default_time = config.get("time", "<8:00AM,10:00AM>")
    default_interval = config.get("interval", "<3,12>")
    logger.debug(f"采用默认签到时间范围 {default_time}, 默认保活间隔天数 {default_interval}.")

    if checkin == "-":
        checkin = default_time

    if emby == "-":
        emby = default_interval

    if subsonic == "-":
        subsonic = default_interval

    if not checkin and not monitor and not emby and not send and not subsonic:
        checkin = default_time
        emby = default_interval
        subsonic = default_interval
        monitor = True
        send = True

    if top and var.console.is_terminal:
        from .top import topper

        asyncio.create_task(topper())

    if play:
        from .embywatcher.main import play_url

        return await play_url(config, play)

    if save:
        from .telechecker.debug import saver

        asyncio.create_task(saver(config))

    if follow:
        from .telechecker.debug import follower

        return await follower(config)

    if analyze:
        from .telechecker.debug import analyzer

        indent = " " * 23
        chats = typer.prompt(indent + "请输入群组用户名 (以空格分隔)").split()
        keywords = typer.prompt(indent + "请输入关键词 (以空格分隔)", default="", show_default=False)
        keywords = keywords.split() if keywords else []
        timerange = typer.prompt(indent + '请输入时间范围 (以"-"分割)', default="", show_default=False)
        timerange = timerange.split("-") if timerange else []
        limit = typer.prompt(indent + "请输入各群组最大获取数量", default=10000, type=int)
        outputs = typer.prompt(indent + "请输入最大输出数量", default=1000, type=int)
        return await analyzer(config, chats, keywords, timerange, limit, outputs)

    if dump:
        from .telechecker.debug import dumper

        return await dumper(config, dump)

    if debug_notify:
        from .telechecker.notify import start_notifier

        if await start_notifier(config):
            logger.info("以下是发送的日志:")
            logger.bind(msg=True, scheme="debugtool").info(
                "这是一条用于测试的即时消息, 使用 debug_notify 触发 😉."
            )
            logger.bind(log=True, scheme="debugtool").info(
                "这是一条用于测试的日志消息, 使用 debug_notify 触发 😉."
            )
            logger.info("已尝试发送, 请至 @embykeeper_bot 查看.")
            await asyncio.sleep(10)
        else:
            logger.error("您当前没有配置有效的日志通知 (未启用日志通知或未配置账号), 请检查配置文件.")
        return

    if emby and not isinstance(emby, int):
        try:
            emby = abs(int(emby))
        except ValueError:
            interval_range_match = re.match(r"<(\d+),(\d+)>", emby)
            if interval_range_match:
                emby = [int(interval_range_match.group(1)), int(interval_range_match.group(2))]
            else:
                logger.error(f"无法解析 Emby 保活间隔天数: {emby}, 保活将不会运行.")
                emby = False

    if subsonic and not isinstance(subsonic, int):
        try:
            subsonic = abs(int(subsonic))
        except ValueError:
            interval_range_match = re.match(r"<(\d+),(\d+)>", subsonic)
            if interval_range_match:
                subsonic = [int(interval_range_match.group(1)), int(interval_range_match.group(2))]
            else:
                logger.error(f"无法解析 Subsonic 保活间隔天数: {subsonic}, 保活将不会运行.")
                subsonic = False

    from .telechecker.notify import start_notifier

    if emby:
        from .embywatcher.main import (
            watcher,
            watcher_continuous,
            watcher_schedule,
            watcher_continuous_schedule,
        )
    if subsonic:
        from .subsonic.main import (
            listener,
            listener_schedule,
        )
    if checkin or monitor or send:
        from .telechecker.main import (
            checkiner,
            checkiner_schedule,
            messager,
            monitorer,
        )

    pool = AsyncTaskPool()

    # 检查是否应该执行保活
    should_run = await should_run_emby(config)

    # 情况1：立即执行模式
    if instant and not debug_cron:
        if emby:
            if should_run:
                pool.add(watcher(config, instant=True))
                pool.add(watcher_continuous(config))
            else:
                logger.info("跳过本次 Emby 保活.")
        if checkin:
            pool.add(checkiner(config, instant=True))
        if subsonic:
            pool.add(listener(config, instant=True))
        await pool.wait()
        logger.debug("启动时立刻执行签到和保活: 已完成.")

    # 情况2：定时任务模式
    if not once:
        if emby:
            try:
                if debug_cron:
                    start_time = end_time = (datetime.now() + timedelta(seconds=10)).time()
                else:
                    watchtime = config.get("watchtime", "<11:00AM,11:00PM>")
                    watchtime_match = re.match(r"<\s*(.*),\s*(.*)\s*>", watchtime)
                    if watchtime_match:
                        start_time, end_time = [
                            parser.parse(watchtime_match.group(i)).time() for i in (1, 2)
                        ]
                    else:
                        start_time = end_time = parser.parse(watchtime).time()
            except parser.ParserError:
                logger.error(
                    "您设定的 watchtime 不正确, 请检查格式. (例如 11:00, <11:00,14:00> / <11:00AM,2:00PM>). 模拟观看保活将不会运行."
                )
            else:
                if should_run:  # 使用之前的检查结果
                    pool.add(
                        watcher_schedule(
                            config,
                            days=0 if debug_cron else emby,
                            start_time=start_time,
                            end_time=end_time,
                        )
                    )
                else:
                    logger.info("跳过本次 Emby 保活计划任务设置.")
        if subsonic:
            try:
                if debug_cron:
                    start_time = end_time = (datetime.now() + timedelta(seconds=10)).time()
                else:
                    listentime = config.get("listentime", "<11:00AM,11:00PM>")
                    listentime_match = re.match(r"<\s*(.*),\s*(.*)\s*>", listentime)
                    if listentime:
                        start_time, end_time = [
                            parser.parse(listentime_match.group(i)).time() for i in (1, 2)
                        ]
                    else:
                        start_time = end_time = parser.parse(listentime).time()
            except parser.ParserError:
                logger.error(
                    "您设定的 listentime 不正确, 请检查格式. (例如 11:00, <11:00,14:00> / <11:00AM,2:00PM>). 模拟观看保活将不会运行."
                )
            else:
                pool.add(
                    listener_schedule(
                        config,
                        days=0 if debug_cron else subsonic,
                        start_time=start_time,
                        end_time=end_time,
                    )
                )
        if checkin:
            try:
                if debug_cron:
                    start_time = end_time = (datetime.now() + timedelta(seconds=10)).time()
                else:
                    checkin_range_match = re.match(r"<\s*(.*),\s*(.*)\s*>", checkin)
                    if checkin_range_match:
                        start_time, end_time = [
                            parser.parse(checkin_range_match.group(i)).time() for i in (1, 2)
                        ]
                    else:
                        start_time = end_time = parser.parse(checkin).time()
            except parser.ParserError:
                logger.error(
                    "您设定的 time 不正确, 请检查格式. (例如 11:00, <11:00,14:00> / <11:00AM,2:00PM>). 自动签到将不会运行."
                )
            else:
                pool.add(
                    checkiner_schedule(
                        config,
                        instant=False,
                        start_time=start_time,
                        end_time=end_time,
                        days=0 if debug_cron else 1,
                    )
                )
        if monitor:
            pool.add(monitorer(config))
        if send:
            pool.add(messager(config))

        async for t in pool.as_completed():
            msg = f"任务 {t.get_name()} "
            try:
                e = t.exception()
                if e:
                    msg += f"发生错误并退出: {e}"
                else:
                    msg += f"成功结束."
            except asyncio.CancelledError:
                msg += f"被取消."
            logger.debug(msg)
            try:
                await t
            except Exception as e:
                logger.error("出现错误, 模块可能停止运行.")
                show_exception(e, regular=False)
                if not config.get("nofail", True):
                    raise


if __name__ == "__main__":
    app()
