from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Dict, Tuple, Union
from asyncio import Task

import psutil
from rich.live import Live
from rich.table import Table
from rich.rule import Rule
from rich.console import Group

from .telegram.session import ClientsSession

from .var import console, tele_used, emby_used

if TYPE_CHECKING:
    from .telegram.pyrogram import Client


async def topper():
    """在控制台底部实时显示系统资源使用情况."""

    process = psutil.Process()

    def get_client_stats(pool: Dict[str, Tuple[Union[Client, Task], int]]) -> Tuple[int, int, int, str]:
        """统计 Client 状态数量"""
        failed = pending = using = idle = 0
        queue_stats = []
        for v in pool.values():
            if not v:
                failed += 1
            if isinstance(v, Task):
                pending += 1
            else:
                client, count = v
                if count > 0:
                    using += 1
                else:
                    idle += 1
                # 获取队列和任务统计
                if hasattr(client, "dispatcher"):
                    try:
                        qsize = client.dispatcher.updates_queue.qsize()
                        tasks = client.dispatcher.handler_worker_tasks
                        active = sum(1 for t in tasks if t.get_coro().cr_await.__name__ != "get")
                        if qsize > 0 or active > 0:
                            # 当队列超过10或handler使用率超过80%时显示红色
                            if qsize >= 10 or (active / len(tasks) >= 0.8):
                                queue_stats.append(f"[red][{qsize}:{active}/{len(tasks)}][/red]")
                            else:
                                queue_stats.append(f"[{qsize}:{active}/{len(tasks)}]")
                    except:
                        queue_stats.append("[Error]")

        queue_text = f" Queue: {' '.join(queue_stats)}" if queue_stats else ""
        return failed, pending, using, idle, queue_text

    def get_ocr_stats():
        """获取OCR子进程状态"""
        children = process.children()
        if not children:
            return None
        total_mem = sum(p.memory_info().rss for p in children) / 1024 / 1024
        return f"OCR: {len(children)} ({total_mem:.1f} MB)"

    def get_stats():
        # 创建状态表格
        table = Table(show_header=False, box=None)

        # 系统资源状态
        mem_mb = process.memory_info().rss / 1024 / 1024
        cpu_percent = process.cpu_percent()
        mem_text = f"[red]{mem_mb:.1f}[/red]" if mem_mb > 1024 else f"{mem_mb:.1f}"
        sys_stats = [
            ("Embykeeper >", "bright_blue"),
            (f"MEM: {mem_text} MB, CPU: {cpu_percent:.1f}%", "bright_blue"),
        ]

        # OCR状态
        ocr_stats = get_ocr_stats()
        if ocr_stats:
            sys_stats.append((ocr_stats, "bright_blue"))

        # Client状态
        if tele_used:
            from .telegram.pyrogram import Dispatcher
            from .telegram.link import Link

            failed, pending, using, idle, queue_text = get_client_stats(ClientsSession.pool)
            client_stats = []
            if failed:
                client_stats.append(f"Failed({failed})")
            if pending:
                client_stats.append(f"Pending({pending})")
            if using:
                client_stats.append(f"Using({using})")
            if idle:
                client_stats.append(f"Idle({idle})")
            if client_stats:
                sys_stats.append((f"Tele: {'/'.join(client_stats)}{queue_text}", "bright_blue"))

            if Link.post_count > 0:
                sys_stats.append((f"Link: {Link.post_count}", "bright_blue"))

            if Dispatcher.updates_count > 0:
                sys_stats.append((f"Updates: {Dispatcher.updates_count}", "bright_blue"))

        if emby_used:
            from .emby.api import Emby

            if Emby.playing_count > 0:
                sys_stats.append((f"Play: {Emby.playing_count}", "bright_blue"))

        table.add_column(style="bright_blue", justify="left")
        for _ in range(len(sys_stats) - 1):
            table.add_column(style="bright_blue", justify="left")

        table.add_row(*[text for text, _ in sys_stats])
        return Group(Rule(style="bright_blue"), table)

    live = Live(
        console=console,
        refresh_per_second=1,
        vertical_overflow="visible",
        auto_refresh=True,
    )
    try:
        live.start()
        while True:
            live.update(get_stats())
            await asyncio.sleep(1)
    except (KeyboardInterrupt, asyncio.CancelledError):
        live.update("")  # 先清空显示内容
        live.stop()  # 然后停止 Live
        raise
