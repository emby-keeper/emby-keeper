import asyncio
from collections import namedtuple
from functools import wraps
import sys
from typing import Any, Iterable, Union

from loguru import logger
import click
from typer import Typer, Exit
from typer.core import TyperCommand

from . import __url__, __name__

Flagged = namedtuple("Flagged", ("noflag", "flag"))


def fail_message(e):
    logger.opt(exception=e).critical(
        f"发生关键错误, {__name__.capitalize()} 将退出, 请在 '{__url__}/issues/new' 提供反馈以帮助作者修复该问题:"
    )


class AsyncTyper(Typer):
    def async_command(self, *args, **kwargs):
        def decorator(async_func):
            @wraps(async_func)
            def sync_func(*_args, **_kwargs):
                try:
                    return asyncio.run(async_func(*_args, **_kwargs))
                except KeyboardInterrupt:
                    print("\r", end="")
                    logger.info("所有客户端已停止, 欢迎您再次使用 Embykeeper.")
                except Exception as e:
                    print("\r", end="")
                    fail_message(e)
                    sys.exit(1)

            self.command(*args, **kwargs)(sync_func)
            return async_func

        return decorator


class FlagValueCommand(TyperCommand):
    def parse_args(self, ctx, args):
        long = {}
        short = {}
        defined = set()
        for o in self.params:
            if isinstance(o, click.Option):
                if isinstance(o.default, Flagged):
                    for pre in o.opts:
                        if pre.startswith("--"):
                            long[pre] = o
                        elif pre.startswith("-"):
                            short[pre] = o

        for i, a in enumerate(args):
            a = a.split("=")
            if a[0] in long:
                defined.add(long[a[0]])
                if len(a) == 1:
                    args[i] = f"{a[0]}={long[a[0]].default.flag}"
            elif a[0] in short:
                defined.add(short[a[0]])
                if len(args) == i + 1 or args[i + 1].startswith("-"):
                    args.insert(i + 1, str(short[a[0]].default.flag))

        for u in set(long.values()) - defined:
            for p, o in long.items():
                if o == u:
                    break
            args.append(f"{p}={u.default.noflag}")

        return super().parse_args(ctx, args)


class AsyncTaskPool:
    def __init__(self):
        self.waiter = asyncio.Condition()
        self.tasks = []

    def add(self, coro):
        async def wrapper():
            task = asyncio.ensure_future(coro)
            await asyncio.wait([task])
            async with self.waiter:
                self.waiter.notify()
                return await task

        t = asyncio.create_task(wrapper())
        self.tasks.append(t)

    async def as_completed(self):
        while True:
            async with self.waiter:
                await self.waiter.wait()
                for t in self.tasks:
                    if t.done():
                        yield t
                        self.tasks.remove(t)


class AsyncCountPool(dict):
    def __init__(self, *args, base=1000, **kw):
        super().__init__(*args, **kw)
        self.lock = asyncio.Lock()
        self.next = base + 1

    async def append(self, value):
        async with self.lock:
            key = self.next
            self[key] = value
            self.next += 1
            return key


def to_iterable(var: Union[Iterable, Any]):
    if var is None:
        return ()
    if isinstance(var, str) or not isinstance(var, Iterable):
        return (var,)
    else:
        return var


def remove_prefix(text: str, prefix: str):
    return text[text.startswith(prefix) and len(prefix) :]


def truncate_str(text: str, length: int):
    return f"{text[:length + 3]}..." if len(text) > length else text


def time_in_range(start, end, x):
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end


def batch(iterable, n=1):
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx : min(ndx + n, l)]


def flatten(l):
    return [item for sublist in l for item in sublist]


def async_partial(f, *args1, **kw1):
    async def func(*args2, **kw2):
        return await f(*args1, *args2, **kw1, **kw2)

    return func


async def idle():
    await asyncio.Event().wait()
