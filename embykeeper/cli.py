import logging
import os
from pathlib import Path
import sys
from typing import List
from functools import wraps

import typer
import asyncio
from loguru import logger
from appdirs import user_data_dir

from . import var, __author__, __name__ as __product__, __url__, __version__
from .utils import AsyncTaskPool, show_exception
from .config import config


class AsyncTyper(typer.Typer):
    def async_command(self, *args, **kwargs):
        def decorator(async_func):
            @wraps(async_func)
            def sync_func(*_args, **_kwargs):
                async def main():
                    try:
                        await async_func(*_args, **_kwargs)
                    except typer.Exit as e:
                        sys.exit(e.exit_code)
                    except Exception as e:
                        print("\r", end="", flush=True)
                        logger.critical(f"发生关键错误, {__name__.capitalize()} 将退出.")
                        show_exception(e, regular=False)
                        sys.exit(1)
                    else:
                        logger.info(f"所有任务已完成, 欢迎您再次使用 {__name__.capitalize()}.")

                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(main())
                except KeyboardInterrupt:
                    print("\r正在停止...\r", end="", flush=True, file=sys.stderr)
                finally:
                    if var.exit_handlers:
                        logger.debug("开始执行退出处理程序.")
                        try:
                            # Wait for exit handlers with timeout
                            loop.run_until_complete(
                                asyncio.wait_for(
                                    asyncio.gather(*[h() for h in var.exit_handlers], return_exceptions=True),
                                    timeout=3,
                                )
                            )
                        except asyncio.TimeoutError:
                            logger.warning("部分退出处理程序超时未完成.")
                        else:
                            logger.debug("退出处理程序执行完成, 开始清理所有任务.")
                    else:
                        logger.debug("未注册退出处理程序, 开始清理所有任务.")

                    # Then cancel remaining tasks
                    tasks = asyncio.all_tasks(loop)
                    for task in tasks:
                        task.cancel()
                    loop.run_until_complete(asyncio.gather(*tasks, return_exceptions=True))
                    loop.run_until_complete(loop.shutdown_asyncgens())
                    print("\r", end="", flush=True)
                    logger.info(f"所有服务已停止并登出, 欢迎您再次使用 {__product__.capitalize()}.")

            self.command(*args, **kwargs)(sync_func)
            return async_func

        return decorator


app = AsyncTyper(
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)


def version(flag):
    if flag:
        print(__version__)
        raise typer.Exit()


def print_example_config(flag):
    if flag:
        print(config.generate_example_config())
        raise typer.Exit()


@app.async_command(
    help=(
        f"欢迎使用 [orange3]{__product__.capitalize()}[/] {__version__} " ":cinema: 无参数默认开启全部功能."
    )
)
async def main(
    config_file: Path = typer.Argument(
        None,
        dir_okay=False,
        allow_dash=True,
        envvar=f"EK_CONFIG_FILE",
        rich_help_panel="参数",
        help="配置文件 (置空以生成)",
    ),
    checkiner: bool = typer.Option(
        False,
        "--checkin",
        "-c",
        rich_help_panel="模块开关",
        help="仅启用 Telegram 签到功能",
    ),
    emby: bool = typer.Option(
        False,
        "--emby",
        "-e",
        rich_help_panel="模块开关",
        help="仅启用 Emby 保活功能",
    ),
    subsonic: bool = typer.Option(
        False,
        "--subsonic",
        "-S",
        rich_help_panel="模块开关",
        help="仅启用 Subsonic 保活功能",
    ),
    monitor: bool = typer.Option(
        False,
        "--monitor",
        "-m",
        rich_help_panel="模块开关",
        help="仅启用群聊监视功能",
    ),
    messager: bool = typer.Option(
        False,
        "--messager",
        "-s",
        rich_help_panel="模块开关",
        help="仅启用自动水群功能",
    ),
    version: bool = typer.Option(
        None,
        "--version",
        "-v",
        rich_help_panel="调试参数",
        callback=version,
        is_eager=True,
        help=f"打印 {__product__.capitalize()} 版本",
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
        False,
        "--once/--cron",
        "-o/-O",
        rich_help_panel="调试参数",
        help="只执行一次而不进入计划执行模式",
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
        False,
        "--simple-log",
        "-L",
        rich_help_panel="调试参数",
        help="简化日志输出格式",
    ),
    disable_color: bool = typer.Option(
        False,
        "--disable-color",
        "-C",
        rich_help_panel="调试参数",
        help="禁用日志颜色",
    ),
    follow: bool = typer.Option(
        False,
        "--follow",
        "-F",
        rich_help_panel="调试工具",
        help="仅启动消息调试",
    ),
    analyze: bool = typer.Option(
        False,
        "--analyze",
        "-A",
        rich_help_panel="调试工具",
        help="仅启动历史信息分析",
    ),
    dump: List[str] = typer.Option(
        [],
        "--dump",
        "-D",
        rich_help_panel="调试工具",
        help="仅启动更新日志",
    ),
    top: bool = typer.Option(
        False,
        "--top",
        "-T",
        rich_help_panel="调试参数",
        help="执行过程中显示系统状态底栏",
    ),
    play: str = typer.Option(
        None,
        "--play-url",
        "-p",
        rich_help_panel="调试工具",
        help="仅模拟观看一个视频",
    ),
    save: bool = typer.Option(
        False,
        "--save",
        rich_help_panel="调试参数",
        help="记录执行过程中的原始更新日志",
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
        None,
        "--basedir",
        "-B",
        rich_help_panel="调试参数",
        help="设定账号文件的位置",
    ),
    noexit: bool = typer.Option(
        False,
        "--noexit",
        "-N",
        rich_help_panel="调试参数",
        help="要求所有长期任务在没有账号时继续监控等待",
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        rich_help_panel="调试参数",
        help="显示或清理 Emby 模拟设备和登陆凭据等缓存",
    ),
):
    from .log import initialize, apply_logging_adapter

    var.debug = verbosity
    if verbosity >= 3:
        level = 0
        logging.getLogger("pyrogram.session").setLevel(20)
        logging.getLogger("hpack").setLevel(20)
        asyncio.get_event_loop().set_debug(True)
        apply_logging_adapter(level=10)
    elif verbosity >= 1:
        level = "DEBUG"
    else:
        level = "INFO"

    initialize(level=level, show_path=verbosity and (not simple_log), show_time=not simple_log)
    if disable_color:
        var.console.no_color = True

    msg = " 您可以通过 Ctrl+C 以结束运行." if not public else ""
    logger.info(f"欢迎使用 [orange3]{__product__.capitalize()}[/]! 正在启动, 请稍等.{msg}")
    logger.info(f"当前版本 ({__version__}) 项目页: {__url__}")
    logger.debug(f'命令行参数: "{" ".join(sys.argv[1:])}".')

    basedir = Path(basedir or user_data_dir(__product__))
    basedir.mkdir(parents=True, exist_ok=True)
    if public:
        logger.info(f'工作目录: "{basedir}"')
    else:
        logger.info(f'工作目录: "{basedir}", 您的用户数据相关文件将存储在此处, 请妥善保管.')
        docker = bool(os.environ.get("EK_IN_DOCKER", False))
        if docker:
            logger.info("当前在 Docker 容器中运行, 请确认该目录已挂载, 否则文件将在容器重建后丢失.")
    if verbosity:
        logger.warning(f"您当前处于调试模式: 日志等级 {verbosity}.")
        app.pretty_exceptions_enable = True

    config.basedir = basedir
    config.windows = windows
    config.public = public

    if public:
        from .public import public_entrypoint

        if not await public_entrypoint():
            raise typer.Exit(1)
    else:
        if not await config.reload_conf(config_file):
            raise typer.Exit(1)

    if verbosity >= 2:
        config.nofail = False
    if not config.nofail:
        logger.warning(f"您当前处于调试模式: 错误将会导致程序停止运行.")
    if debug_cron:
        config.debug_cron = True
        logger.warning("您当前处于计划任务调试模式, 将在 10 秒后运行计划任务.")
    config.noexit = noexit

    if not checkiner and not monitor and not emby and not messager and not subsonic:
        checkiner = True
        emby = True
        subsonic = True
        monitor = True
        messager = True

    if config.mongodb:
        logger.info(f"正在连接到 MongoDB 缓存, 请稍候.")
        try:
            from .cache import cache

            cache.set("test", "test")
            assert cache.get("test", None) == "test"
            cache.delete("test")
        except Exception as e:
            logger.error(f"MongoDB 缓存连接失败: {e}, 程序将退出.")
            show_exception(e, regular=False)
            return

    if clean:
        from .clean import cleaner

        return await cleaner()

    if follow:
        from .telegram.debug import follower

        return await follower()

    if top:
        from .topper import topper

        if not (var.console.is_terminal and var.console.is_interactive):
            logger.warning("在非交互模式下启用底栏可能会导致显示异常.")
        asyncio.create_task(topper())

    if play:
        from .emby.main import EmbyManager

        return await EmbyManager().play_url(play)

    if save:
        from .telegram.debug import saver

        asyncio.create_task(saver())

    if analyze:
        from .telegram.debug import analyzer

        indent = " " * 23
        chats = typer.prompt(indent + "请输入群组用户名 (以空格分隔)").split()
        keywords = typer.prompt(indent + "请输入关键词 (以空格分隔)", default="", show_default=False)
        keywords = keywords.split() if keywords else []
        timerange = typer.prompt(indent + '请输入时间范围 (以"-"分割)', default="", show_default=False)
        timerange = timerange.split("-") if timerange else []
        limit = typer.prompt(indent + "请输入各群组最大获取数量", default=10000, type=int)
        outputs = typer.prompt(indent + "请输入最大输出数量", default=1000, type=int)
        return await analyzer(chats, keywords, timerange, limit, outputs)

    if dump:
        from .telegram.debug import dumper

        return await dumper(dump)

    if debug_notify:
        from .telegram.debug import debug_notifier

        return await debug_notifier()

    try:
        checkin_man = None
        if checkiner:
            from .telegram.checkin_main import CheckinerManager

            checkin_man = CheckinerManager()

        monitor_man = None
        if monitor:
            from .telegram.monitor_main import MonitorManager

            monitor_man = MonitorManager()

        message_man = None
        if messager:
            from .telegram.message_main import MessageManager

            message_man = MessageManager()

        emby_man = None
        if emby:
            from .emby.main import EmbyManager

            emby_man = EmbyManager()

        subsonic_man = None
        if subsonic:
            from .subsonic.main import SubsonicManager

            subsonic_man = SubsonicManager()

        pool = AsyncTaskPool()
        if instant and not debug_cron:
            if checkin_man:
                pool.add(checkin_man.run_all(instant=True), "站点签到")
            if emby_man:
                pool.add(emby_man.run_all(instant=True), "Emby 保活")
            if subsonic_man:
                pool.add(subsonic_man.run_all(instant=True), "Subsonic 保活")
            await pool.wait()
            logger.debug("启动时立刻执行签到和保活: 已完成.")
        streams = None
        if config.notifier.enabled:
            from .telegram.notify import start_notifier

            streams = await start_notifier()
        if not once:
            if checkin_man:
                pool.add(checkin_man.schedule_all(), "站点签到")
            if monitor_man:
                pool.add(monitor_man.run_all(), "群组监控")
            if message_man:
                pool.add(message_man.run_all(), "自动水群")
            if emby_man:
                pool.add(emby_man.schedule_all(), "Emby 保活")
            if subsonic_man:
                pool.add(subsonic_man.schedule_all(), "Subsonic 保活")
        if config.noexit:
            logger.info("处于长期监控模式, 当没有账号时将继续监控等待新配置.")
            pool.add(asyncio.Event().wait(), "账号配置文件监控")
        try:
            async for t in pool.as_completed():
                try:
                    await t
                except asyncio.CancelledError:
                    logger.debug(f"任务 {t.get_name()} 被取消.")
                except Exception as e:
                    logger.debug(f"任务 {t.get_name()} 出现错误, 模块可能停止运行.")
                    show_exception(e, regular=False)
                    if not config.nofail:
                        raise
                else:
                    logger.debug(f"任务 {t.get_name()} 成功结束.")
        finally:
            if streams:
                await asyncio.gather(*[stream.join() for stream in streams])
    finally:
        from .runinfo import RunContext

        RunContext.cancel_all()


if __name__ == "__main__":
    app()
