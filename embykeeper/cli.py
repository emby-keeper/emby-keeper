import json
import logging
import os
from pathlib import Path
import sys
from typing import List, Optional
from functools import wraps

import typer
from typer.core import TyperCommand
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
                        return e.exit_code
                    except Exception as e:
                        print("\r", end="", flush=True)
                        logger.critical(f"发生关键错误, {__product__.capitalize()} 将退出.")
                        show_exception(e, regular=False)
                        return 1
                    else:
                        logger.info(f"所有任务已完成, 欢迎您再次使用 {__product__.capitalize()}.")

                returncode = 130
                try:
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    returncode = loop.run_until_complete(main())
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
                    raise typer.Exit(returncode)

            self.command(*args, **kwargs)(sync_func)
            return async_func

        return decorator


class EmbykeeperCommand(TyperCommand):
    def main(self, args=None, prog_name=None, **kwargs):
        arguments = list(sys.argv[1:] if args is None else args)
        if arguments and arguments[0] == "web":
            from embykeeperapi.app import cli as panel_cli

            return panel_cli(args=arguments[1:], prog_name=f"{prog_name or 'embykeeper'} web", **kwargs)
        return super().main(args=arguments, prog_name=prog_name, **kwargs)


app = AsyncTyper(
    pretty_exceptions_enable=False,
    rich_markup_mode="rich",
    add_completion=False,
    add_help_option=False,
)


def version(flag):
    if flag:
        print(__version__)
        raise typer.Exit()


def print_example_config(flag):
    if flag:
        print(config.generate_example_config())
        raise typer.Exit()


def print_help(ctx: typer.Context, param: typer.CallbackParam, value: bool):
    if not value or ctx.resilient_parsing:
        return
    typer.echo(ctx.get_help())
    raise typer.Exit()


async def _prepare_mongodb_source(mongodb_url: str, config_file: Path = None) -> bool:
    """Use MongoDB for both the config document and the runtime cache."""

    from .config_source import ConfigSourceError, MongoConfigSource
    from .schema import Config as CoreConfig

    logger.info("正在连接到 MongoDB, 配置与缓存将全部保存在数据库中.")
    try:
        source = MongoConfigSource(mongodb_url)
        source.check()
    except ConfigSourceError as exc:
        logger.error(f"{exc}, 程序将退出.")
        return False

    config.set_source(source)
    _migrate_local_state(source, config_file)
    config.set(CoreConfig(mongodb=mongodb_url))
    if not await config.reload_conf():
        return False
    # A stored document may not carry the connection string, keep the cache on MongoDB.
    config.mongodb = mongodb_url
    return True


def _migrate_local_state(source, config_file: Path = None, basedir: Path = None) -> None:
    """Import a leftover file-based config and cache once, on first MongoDB start."""

    from .config_source import ConfigSourceError, FileConfigSource
    from .schema import Config as CoreConfig

    data_dir = Path(basedir) if basedir else config.basedir
    try:
        if not source.read():
            legacy = Path(config_file) if config_file else data_dir / "config.toml"
            data = FileConfigSource(legacy).read() if legacy.exists() else {}
            if data:
                CoreConfig(**data)
                source.write(data)
                logger.info(f'已将 "{legacy}" 中的配置导入 MongoDB.')
    except ConfigSourceError as exc:
        logger.warning(f"导入本地配置到 MongoDB 失败: {exc}")
    except Exception as exc:
        logger.warning(f"本地配置文件无效, 未导入 MongoDB: {exc}")

    cache_file = data_dir / "cache.json"
    if not cache_file.exists():
        return
    try:
        if not source.cache_empty():
            return
        items = json.loads(cache_file.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning(f'读取 "{cache_file}" 失败, 未导入缓存: {exc}')
        return
    except ConfigSourceError as exc:
        logger.warning(f"检查 MongoDB 缓存失败: {exc}")
        return
    if not isinstance(items, dict) or not items:
        return
    try:
        count = source.import_cache(items)
    except Exception as exc:
        logger.warning(f"导入本地缓存到 MongoDB 失败: {exc}")
        return
    cache_file.rename(cache_file.with_suffix(".json.migrated"))
    logger.info(f'已将 "{cache_file}" 中的 {count} 条缓存导入 MongoDB.')


@app.async_command(
    cls=EmbykeeperCommand,
    epilog="网页管理: embykeeper web",
    help=(
        f"欢迎使用 [orange3]{__product__.capitalize()}[/] {__version__} " ":cinema: 无参数默认开启全部功能."
    ),
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
    help: bool = typer.Option(
        None,
        "--help",
        "-h",
        callback=print_help,
        is_eager=True,
        rich_help_panel="调试参数",
        help="显示此帮助信息并退出.",
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
    registrar: bool = typer.Option(
        False,
        "--registrar",
        "-r",
        rich_help_panel="模块开关",
        help="仅启用注册功能",
    ),
    registrar_bot: Optional[str] = typer.Option(
        None,
        "--registrar-bot",
        "-R",
        rich_help_panel="模块开关",
        help="快速反复尝试注册指定机器人 (Embyboss)",
    ),
    api: bool = typer.Option(
        False,
        "--api",
        "-a",
        rich_help_panel="模块开关",
        help="启动 API 服务器模式",
    ),
    api_host: str = typer.Option(
        "0.0.0.0",
        "--api-host",
        rich_help_panel="模块开关",
        help="API 服务器绑定地址",
    ),
    api_port: int = typer.Option(
        8000,
        "--api-port",
        rich_help_panel="模块开关",
        help="API 服务器端口",
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
        "--debug-cron",
        envvar="EK_DEBUG_CRON",
        show_envvar=False,
        rich_help_panel="调试工具",
        help="开启任务调试模式, 在三秒后立刻开始执行计划任务",
    ),
    debug_notify: bool = typer.Option(
        False,
        "--debug-notify",
        show_envvar=False,
        rich_help_panel="调试工具",
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
    telegram_test_server: bool = typer.Option(
        False,
        "--telegram-test-server",
        rich_help_panel="调试参数",
        hidden=True,
        help="使用 Telegram 测试服务器",
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
        rich_help_panel="调试工具",
        help="显示或清理 Emby 模拟设备和登陆凭据等缓存",
    ),
):
    from .log import initialize, apply_logging_adapter

    var.debug = verbosity
    if verbosity >= 3:
        level = 0
        if verbosity < 4:
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
    var.telegram_test_server = telegram_test_server
    if telegram_test_server:
        logger.warning("您当前处于 Telegram 测试服务器模式, 请谨慎使用.")

    config.basedir = basedir
    config.windows = windows
    config.public = public

    if public:
        from .public import public_preparation

        if not await public_preparation():
            raise typer.Exit(1)
    else:
        mongodb_url = os.environ.get("EK_MONGODB", "").strip()
        if mongodb_url:
            if not await _prepare_mongodb_source(mongodb_url, config_file):
                raise typer.Exit(1)
        elif not await config.reload_conf(config_file):
            raise typer.Exit(1)

    if api:
        logger.info(f"启动 API 服务器模式, 监听 {api_host}:{api_port}")
        import uvicorn
        from .api import create_app

        app = create_app()
        config_obj = uvicorn.Config(
            app,
            host=api_host,
            port=api_port,
            access_log=verbosity >= 1,
            log_config=None,
        )
        server = uvicorn.Server(config_obj)
        await server.serve()
        return

    if verbosity >= 2:
        config.nofail = False
    if not config.nofail:
        logger.warning(f"您当前处于调试模式: 错误将会导致程序停止运行.")
    if debug_cron:
        config.debug_cron = True
        logger.warning("您当前处于计划任务调试模式, 将在 10 秒后运行计划任务.")
    config.noexit = noexit

    if not checkiner and not monitor and not emby and not messager and not subsonic and not registrar:
        checkiner = True
        emby = True
        subsonic = True
        monitor = True
        messager = True
        registrar = True

    if config.mongodb and not var.use_mongodb_config:
        if config.proxy:
            logger.warning("由于不支持, 不使用设定的代理连接 MongoDB 服务器.")
        if not public:
            logger.warning("在本地部署模式下, 不推荐设定使用 MongoDB 缓存.")
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
    else:
        try:
            from .cache import cache

            cache.set("test", "test")
            assert cache.get("test", None) == "test"
            cache.delete("test")
        except Exception as e:
            logger.error(f"本地缓存读写失败: {e}, 请使用 MongoDB 缓存, 程序将退出.")
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
        from .notify import debug_notifier

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

        register_man = None
        if registrar or registrar_bot:
            from .telegram.registrar_main import RegisterManager

            register_man = RegisterManager()

        emby_man = None
        if emby:
            from .emby.main import EmbyManager

            emby_man = EmbyManager()

        subsonic_man = None
        if subsonic:
            from .subsonic.main import SubsonicManager

            subsonic_man = SubsonicManager()

        pool = AsyncTaskPool()
        telegram_runtime_tasks = {}
        media_runtime_tasks = {}
        runtime_restart_lock = asyncio.Lock()

        async def await_runtime_task(task: asyncio.Task):
            return await task

        def track_runtime_task(task_store: dict, name: str, coro, description: str):
            task = asyncio.create_task(coro, name=description)
            task_store[name] = task

            def on_done(t: asyncio.Task, key: str = name, store: dict = task_store):
                if store.get(key) is t:
                    del store[key]

            task.add_done_callback(on_done)
            pool.add(await_runtime_task(task), description)
            return task

        def start_telegram_runtime_tasks(targets=None):
            selected = set(targets or ("checkiner", "registrar", "monitor", "messager"))
            if "checkiner" in selected and checkin_man:
                track_runtime_task(
                    telegram_runtime_tasks, "checkiner", checkin_man.schedule_all(), "站点签到"
                )
            if "registrar" in selected and register_man:
                track_runtime_task(telegram_runtime_tasks, "registrar", register_man.start(), "站点注册")
            if "monitor" in selected and monitor_man:
                track_runtime_task(telegram_runtime_tasks, "monitor", monitor_man.run_all(), "群组监控")
            if "messager" in selected and message_man:
                track_runtime_task(telegram_runtime_tasks, "messager", message_man.run_all(), "自动水群")

        def start_media_runtime_tasks(targets=None):
            selected = set(targets or ("emby", "subsonic"))
            if "emby" in selected and emby_man:
                track_runtime_task(media_runtime_tasks, "emby", emby_man.schedule_all(), "Emby 保活")
            if "subsonic" in selected and subsonic_man:
                track_runtime_task(
                    media_runtime_tasks, "subsonic", subsonic_man.schedule_all(), "Subsonic 保活"
                )

        async def cancel_runtime_tasks(task_store: dict, targets):
            selected = set(targets)
            current_tasks = [
                task_store.get(name)
                for name in selected
                if task_store.get(name) and not task_store.get(name).done()
            ]
            for task in current_tasks:
                task.cancel()
            if current_tasks:
                await asyncio.gather(*current_tasks, return_exceptions=True)
            for name in selected:
                task_store.pop(name, None)

        def has_active_telegram_accounts(attr: str):
            accounts = config.telegram.account if config.telegram and config.telegram.account else []
            return any(account.enabled and getattr(account, attr, False) for account in accounts)

        def telegram_checkiner_active():
            return bool(
                checkin_man
                and config.checkiner
                and config.checkiner.enabled
                and has_active_telegram_accounts("checkiner")
            )

        def telegram_monitor_active():
            return bool(
                monitor_man
                and config.monitor
                and config.monitor.enabled
                and has_active_telegram_accounts("monitor")
            )

        def telegram_messager_active():
            return bool(
                message_man
                and config.messager
                and config.messager.enabled
                and has_active_telegram_accounts("messager")
            )

        def telegram_registrar_active():
            return bool(
                register_man
                and config.registrar
                and config.registrar.enabled
                and has_active_telegram_accounts("registrar")
            )

        def notifier_uses_telegram_proxy():
            return bool(
                config.notifier
                and config.notifier.enabled
                and config.notifier.method == "telegram"
                and config.telegram
                and config.telegram.use_proxy
            )

        def get_telegram_use_proxy_restart_targets():
            targets = set()
            if telegram_checkiner_active():
                targets.add("checkiner")
            if telegram_monitor_active():
                targets.add("monitor")
            if telegram_messager_active():
                targets.add("messager")
            if telegram_registrar_active():
                targets.add("registrar")
            return targets

        def get_proxy_telegram_restart_targets():
            targets = set()

            if config.telegram and config.telegram.use_proxy:
                if telegram_checkiner_active():
                    targets.add("checkiner")
                if telegram_monitor_active():
                    targets.add("monitor")
                if telegram_messager_active():
                    targets.add("messager")
                if telegram_registrar_active():
                    targets.add("registrar")

            return targets

        def get_proxy_media_restart_targets():
            targets = set()

            emby_accounts = config.emby.account if config.emby and config.emby.account else []
            if (
                emby_man
                and config.emby
                and config.emby.enabled
                and any(a.enabled and a.use_proxy for a in emby_accounts)
            ):
                targets.add("emby")

            subsonic_accounts = config.subsonic.account if config.subsonic and config.subsonic.account else []
            if (
                subsonic_man
                and config.subsonic
                and config.subsonic.enabled
                and any(a.enabled and a.use_proxy for a in subsonic_accounts)
            ):
                targets.add("subsonic")

            return targets

        async def restart_telegram_runtime_locked(reason: str, targets, clean_sessions: bool = False):
            selected = set(targets)
            if not selected and not clean_sessions:
                return

            logger.bind(scheme="config").warning(
                f"检测到 {reason} 变更, 正在重启受影响的 Telegram 相关模块以应用新设置."
            )

            await cancel_runtime_tasks(telegram_runtime_tasks, selected)

            if "checkiner" in selected and checkin_man:
                checkin_man.stop_all()
            if "registrar" in selected and register_man:
                register_man.stop_all()
            if "monitor" in selected and monitor_man:
                monitor_man.stop_all()
            if "messager" in selected and message_man:
                message_man.stop_all()

            if clean_sessions:
                from .telegram.session import ClientsSession

                await ClientsSession.clean_all(force=True)

            if selected:
                start_telegram_runtime_tasks(selected)

            logger.info("Telegram 受影响模块已按新的代理设置重新启动.")

        async def restart_media_runtime_locked(reason: str, targets):
            selected = set(targets)
            if not selected:
                return

            logger.bind(scheme="config").warning(
                f"检测到 {reason} 变更, 正在重启受影响的媒体保活模块以应用新设置."
            )

            await cancel_runtime_tasks(media_runtime_tasks, selected)

            if "emby" in selected and emby_man:
                emby_man.stop_all()
            if "subsonic" in selected and subsonic_man:
                subsonic_man.stop_all()

            start_media_runtime_tasks(selected)
            logger.info("媒体保活模块已按新的代理设置重新启动.")

        async def handle_telegram_use_proxy_change_async(*args):
            if once:
                return

            targets = get_telegram_use_proxy_restart_targets()
            clean_sessions = bool(targets) or notifier_uses_telegram_proxy()
            if not targets and not clean_sessions:
                return

            async with runtime_restart_lock:
                await restart_telegram_runtime_locked("Telegram 代理设置", targets, clean_sessions=True)

        async def handle_proxy_change_async(*args):
            if once:
                return

            telegram_targets = get_proxy_telegram_restart_targets()
            media_targets = get_proxy_media_restart_targets()
            clean_telegram_sessions = notifier_uses_telegram_proxy() or bool(
                config.telegram and config.telegram.use_proxy and telegram_targets
            )

            if not telegram_targets and not media_targets and not clean_telegram_sessions:
                logger.bind(scheme="config").info(
                    "检测到代理设置变更, 当前没有运行中的模块依赖该代理, 跳过重启."
                )
                return

            async with runtime_restart_lock:
                await restart_telegram_runtime_locked(
                    "代理设置", telegram_targets, clean_sessions=clean_telegram_sessions
                )
                await restart_media_runtime_locked("代理设置", media_targets)

        def handle_telegram_use_proxy_change(*args):
            asyncio.create_task(handle_telegram_use_proxy_change_async(*args))

        def handle_proxy_change(*args):
            asyncio.create_task(handle_proxy_change_async(*args))

        config.on_change("telegram.use_proxy", handle_telegram_use_proxy_change)
        config.on_change("proxy", handle_proxy_change)

        if registrar_bot:
            logger.info(f"开始快速注册 @{registrar_bot}")
            if register_man:
                await register_man.run_single_bot(registrar_bot, instant=True)
            else:
                logger.error("注册管理器未初始化")
            return

        if instant and not debug_cron:
            if checkin_man:
                pool.add(checkin_man.run_all(instant=True), "站点签到")
            if emby_man:
                pool.add(emby_man.run_all(instant=True), "Emby 保活")
            if subsonic_man:
                pool.add(subsonic_man.run_all(instant=True), "Subsonic 保活")
            await pool.wait()
            logger.debug("启动时立刻执行签到和保活: 已完成.")
        if (not once) or config.noexit:
            from .notify import start_notifier

            streams = await start_notifier()
        if not once:
            start_telegram_runtime_tasks()
            start_media_runtime_tasks()
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
