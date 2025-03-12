from __future__ import annotations

import inspect
from logging import Formatter
import asyncio
import logging
from typing import TYPE_CHECKING

from loguru import logger
from rich.logging import RichHandler
from rich.text import Text

from . import var
from .utils import to_iterable

if TYPE_CHECKING:
    from loguru import Logger

pad = " " * 23

scheme_names = {
    "telegram": "Telegram",
    "telechecker": "每日签到",
    "telemonitor": "消息监控",
    "telemessager": "定时水群",
    "telelink": "账号服务",
    "telenotifier": "消息推送",
    "embywatcher": "Emby保活",
    "subsonic": "Subsonic保活",
    "datamanager": "下载器",
    "debugtool": "开发工具",
    "config": "配置文件",
    "cfsolver": "验证解析",
}


def formatter(record):
    """根据日志器的 scheme 属性配置输出格式."""
    extra = record["extra"]
    scheme = extra.get("scheme", None)

    def ifextra(keys, pattern="{}"):
        keys = to_iterable(keys)
        if all(k in extra for k in keys):
            return pattern.format(*[f"{{extra[{k}]}}" for k in keys])
        else:
            return ""

    if scheme in ("telegram", "telechecker", "telemonitor", "telemessager", "telelink"):
        username = ifextra("username", " ([cyan]{}[/])")
        name = ifextra("name", "([magenta]{}[/]) ")
        return f"[blue]{scheme_names[scheme]}[/]{username}: {name}{{message}}"
    elif scheme == "embywatcher":
        ident = ifextra(["username", "server"], " ([cyan]{}@{}[/])")
        return f"[blue]{scheme_names[scheme]}[/]{ident}: {{message}}"
    elif scheme == "subsonic":
        ident = ifextra(["username", "server"], " ([cyan]{}@{}[/])")
        return f"[blue]{scheme_names[scheme]}[/]{ident}: {{message}}"
    elif scheme in ("datamanager", "debugtool", "config", "cfsolver"):
        return f"[blue]{scheme_names[scheme]}[/]: {{message}}"
    else:
        return "{message}"


def initialize(level="INFO", **kw):
    """初始化日志配置."""

    from asyncio import constants

    logger.remove()
    handler = RichHandler(
        console=var.console, markup=True, rich_tracebacks=True, tracebacks_suppress=[asyncio], **kw
    )
    handler.setFormatter(Formatter(None, "[%m/%d %H:%M]"))
    logger.add(handler, format=formatter, level=level, colorize=False)

    constants.LOG_THRESHOLD_FOR_CONNLOST_WRITES = 1000000


class InterceptHandler(logging.Handler):
    """A logging handler that intercepts standard logging messages and redirects them to loguru."""

    def __init__(self, level: int = 0):
        super().__init__(level)

    def emit(self, record):
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1
        text = record.getMessage()
        text = Text.from_ansi(text).plain
        text = f"[{level}] ({record.name}) {text}"
        logger.opt(depth=depth, exception=record.exc_info).debug(text)


def apply_logging_adapter(level: int = 20):
    logging.basicConfig(handlers=[InterceptHandler()], level=level, force=True)
