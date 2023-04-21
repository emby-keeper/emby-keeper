import asyncio
import inspect
import logging
import operator
import pkgutil
import random
from logging import StreamHandler
from typing import List, Type
from importlib import import_module

from dateutil import parser
from pyrogram.enums import ChatType
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message, Update
from rich import box
from rich.live import Live
from rich.panel import Panel
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn
from rich.table import Column, Table
from rich.text import Text
from rich.pretty import pprint

from ..utils import batch, flatten, idle, time_in_range, async_partial
from ..log import logger, formatter
from . import __name__
from .link import Link, TelegramStream
from .tele import Client, ClientsSession
from .bots.base import BaseBotCheckin

logger = logger.bind(scheme="telegram")


def get_spec(type: str):
    if type == "checkiner":
        sub = "bots"
        suffix = "checkin"
    elif type == "monitor":
        sub = "monitor"
        suffix = "monitor"
    elif type == "messager":
        sub = "messager"
        suffix = "messager"
    else:
        raise ValueError(f"{type} is not a valid service.")
    return sub, suffix


def get_names(type: str) -> List[str]:
    sub, _ = get_spec(type)
    results = []
    typemodule = import_module(f"{__name__}.{sub}")
    for _, mn, _ in pkgutil.iter_modules(typemodule.__path__):
        module = import_module(f"{__name__}.{sub}.{mn}")
        if not getattr(module, "__ignore__", False):
            results.append(mn)
    return results


def get_cls(type: str, names: List[str] = None) -> List[Type]:
    sub, suffix = get_spec(type)
    if names == None:
        names = get_names(type)
    results = []
    for name in names:
        module = import_module(f"{__name__}.{sub}.{name}")
        for cn, cls in inspect.getmembers(module, inspect.isclass):
            if (name.replace("_", "") + suffix).lower() == cn.lower():
                results.append(cls)
    return results


def extract(clss: List[Type]) -> List[Type]:
    extracted = []
    for cls in clss:
        ncs = [c for c in cls.__dict__.values() if inspect.isclass(c)]
        if ncs:
            extracted.extend(ncs)
        else:
            extracted.append(cls)
    return extracted


async def dump_message(client: Client, message: Message, table: Table):
    text = message.text or message.caption
    if text:
        text = text.replace("\n", " ")
        if not text:
            return
    else:
        return
    if message.from_user:
        user = message.from_user
        sender_id = str(user.id)
        sender_icon = "👤"
        if message.outgoing:
            sender = Text("Me", style="bold red")
            text = Text(text, style="red")
        else:
            sender = user.name
            if user.is_bot:
                sender_icon = "🤖"
                sender = Text(sender, style="bold yellow")
    else:
        sender = sender_id = sender_icon = None

    chat_id = "{: }".format(message.chat.id)
    if message.chat.type == ChatType.GROUP or message.chat.type == ChatType.SUPERGROUP:
        chat = message.chat.title
        chat_icon = "👥"
    elif message.chat.type == ChatType.CHANNEL:
        chat = message.chat.title
        chat_icon = "📢"
    elif message.chat.type == ChatType.BOT:
        chat = None
        chat_icon = "🤖"
    else:
        chat = chat_icon = None
    return table.add_row(
        f"{client.me.name}",
        "│",
        chat_icon,
        chat,
        chat_id,
        "│",
        sender_icon,
        sender,
        sender_id,
        "│",
        text,
    )


async def checkin_task(checkiner: BaseBotCheckin, sem, wait=0):
    await asyncio.sleep(wait)
    async with sem:
        return await checkiner._start()


async def gather_task(tasks, username):
    return username, await asyncio.gather(*tasks)


async def checkiner(config: dict, instant=False):
    async with ClientsSession.from_config(config) as clients:
        coros = []
        async for tg in clients:
            log = logger.bind(scheme="telechecker", username=tg.me.name)
            if not await Link(tg).auth("checkiner"):
                log.error(f"功能初始化失败: 权限校验不通过.")
                continue
            sem = asyncio.Semaphore(int(config.get("concurrent", 1)))
            clses = extract(get_cls("checkiner", names=config.get("service", {}).get("checkiner", None)))
            checkiners = [
                cls(
                    tg,
                    retries=config.get("retries", 10),
                    timeout=config.get("timeout", 120),
                    nofail=config.get("nofail", True),
                )
                for cls in clses
            ]
            tasks = []
            for c in checkiners:
                wait = 0 if instant else random.randint(0, 60 * config.get("random", 15))
                task = asyncio.create_task(checkin_task(c, sem, wait))
                tasks.append(task)
            coros.append(gather_task(tasks, username=tg.me.name))
        while coros:
            done, coros = await asyncio.wait(coros, return_when=asyncio.FIRST_COMPLETED)
            for t in done:
                username, results = await t
                log = logger.bind(scheme="telechecker", username=username)
                failed = []
                ignored = []
                successful = []
                for i, c in enumerate(checkiners):
                    if results[i] == False:
                        failed.append(c)
                    elif results[i] is None:
                        ignored.append(c)
                    else:
                        successful.append(c)
                spec = f"共{len(checkiners)}个"
                if successful:
                    spec += f", {len(successful)}成功"
                elif failed:
                    spec += f", {len(failed)}失败"
                elif ignored:
                    spec += f", {len(ignored)}跳过"
                if failed:
                    log.error(f"签到失败 ({spec}): {','.join([f.name for f in failed])}")
                else:
                    log.bind(notify=True).info(f"签到成功 ({spec}).")


async def monitorer(config: dict):
    jobs = []
    async with ClientsSession.from_config(config, monitor=True) as clients:
        async for tg in clients:
            log = logger.bind(scheme="telemonitor", username=tg.me.name)
            if not await Link(tg).auth("monitorer"):
                log.error(f"功能初始化失败: 权限校验不通过.")
                continue
            clses = extract(get_cls("monitor", names=config.get("service", {}).get("monitor", None)))
            names = []
            for cls in clses:
                jobs.append(asyncio.create_task(cls(tg, nofail=config.get("nofail", True))._start()))
                names.append(cls.name)
            if names:
                log.info(f'已启用监控器: {",".join(names)}')
        await asyncio.gather(*jobs)


async def messager(config: dict, scheduler):
    async with ClientsSession.from_config(config, send=True) as clients:
        async for tg in clients:
            log = logger.bind(scheme="telemessager", username=tg.me.name)
            if not await Link(tg).auth("messager"):
                log.error(f"功能初始化失败: 权限校验不通过.")
                continue
            clses = extract(get_cls("messager", names=config.get("service", {}).get("messager", None)))
            for cls in clses:
                cls(
                    {"api_id": tg.api_id, "api_hash": tg.api_hash, "phone": tg.phone_number},
                    scheduler,
                    username=tg.me.name,
                    proxy=config.get("proxy", None),
                    nofail=config.get("nofail", True),
                ).start()


async def follower(config: dict):
    columns = [
        Column("用户", style="cyan", justify="center"),
        Column("", max_width=1, style="white"),
        Column("", max_width=2, overflow="crop"),
        Column("会话", style="bright_blue", no_wrap=True, justify="right", max_width=15),
        Column("(ChatID)", style="gray50", min_width=14, max_width=20),
        Column("", max_width=1, style="white"),
        Column("", max_width=2, overflow="crop"),
        Column("发信人", style="green", no_wrap=True, max_width=15, justify="right"),
        Column("(UserID)", style="gray50", min_width=10, max_width=15),
        Column("", max_width=1, style="white"),
        Column("信息", no_wrap=True, min_width=40, max_width=60),
    ]
    async with ClientsSession.from_config(config) as clients:
        table = Table(*columns, header_style="bold magenta", box=box.SIMPLE)
        async for tg in clients:
            tg.add_handler(MessageHandler(async_partial(dump_message, table=table)))
        with Live(table, refresh_per_second=4, vertical_overflow="visible"):
            await idle()


async def analyzer(config: dict, chats, keywords, timerange, limit=2000):
    def render_page(progress, texts):
        page = Table.grid()
        page.add_row(Panel(progress))
        if texts:
            msgs = sorted(texts.items(), key=operator.itemgetter(1), reverse=True)
            columns = flatten([[Column(max_width=15, no_wrap=True), Column(min_width=2)] for _ in range(4)])
            table = Table(*columns, show_header=False, box=box.SIMPLE)
            cols = []
            for col in batch(msgs, 12):
                col = [(t.split()[0], str(c)) for t, c in col]
                col += [("", "")] * (12 - len(col))
                cols.append(col)
                if len(cols) >= 4:
                    break
            for row in map(list, zip(*cols)):
                table.add_row(*flatten(row))
            page.add_row(table)
        return page

    texts = {}
    if timerange:
        start, end = (parser.parse(t).time() for t in timerange)
    async with ClientsSession.from_config(config) as clients:
        async for tg in clients:
            target = f"{tg.me.name}.msgs"
            logger.info(f'开始分析账号: "{tg.me.name}", 结果将写入"{target}".')
            pcs = list(Progress.get_default_columns())
            pcs.insert(0, SpinnerColumn())
            pcs.insert(3, MofNCompleteColumn(table_column=Column(justify="center")))
            p = Progress(*pcs, transient=True)
            with Live(render_page(p, texts)) as live:
                updates = 0
                pchats = p.add_task("[red]会话: ", total=len(chats))
                for c in chats:
                    c = c.rsplit("/", 1)[-1]
                    pmsgs = p.add_task("[red]记录: ", total=limit)
                    async for m in tg.get_chat_history(c, limit=limit):
                        if m.text:
                            if (not keywords) or any(s in m.text for s in keywords):
                                if (not timerange) or time_in_range(start, end, m.date.time()):
                                    if m.text in texts:
                                        texts[m.text] += 1
                                    else:
                                        texts[m.text] = 1
                                    updates += 1
                                    if updates % 200 == 0:
                                        live.update(render_page(p, texts))
                        p.advance(pmsgs)
                    p.update(pmsgs, visible=False)
                    p.advance(pchats)
            with open(target, "w+") as f:
                f.writelines(
                    [
                        f"{t}\t{c}\n"
                        for t, c in sorted(texts.items(), key=operator.itemgetter(1), reverse=True)
                    ]
                )


async def notifier(config: dict):
    def _filter(record):
        notify = record.get("extra", {}).get("notify", None)
        if notify or record["level"].no == logging.ERROR:
            return True
        else:
            return False

    def _formatter(record):
        notify = record.get("extra", {}).get("notify", False)
        format = formatter(record)
        if notify and notify != True:
            format = format.replace("{message}", "{extra[notify]}")
        return "{level}#" + format

    accounts = config.get("telegram", [])
    notifier = config.get("notifier", None)
    if notifier:
        try:
            if notifier == True:
                notifier = accounts[0]
            elif isinstance(notifier, int):
                notifier = accounts[notifier + 1]
            elif isinstance(notifier, str):
                for a in accounts:
                    if a["phone"] == notifier:
                        notifier = a
                        break
            else:
                notifier = None
        except IndexError:
            notifier = None
    if notifier:
        async with ClientsSession([notifier], proxy=config.get("proxy", None)) as clients:
            async for tg in clients:
                logger.info(f'计划任务的关键消息将通过 Embykeeper Bot 发送至 "{tg.phone_number}" 账号.')
                logger.add(StreamHandler(TelegramStream(link=Link(tg))), format=_formatter, filter=_filter)
            await idle()
