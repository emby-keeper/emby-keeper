import asyncio
import inspect
import operator
import random
from functools import partial

from dateutil import parser
from loguru import logger
from pyrogram.enums import ChatType
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from rich import box
from rich.live import Live
from rich.panel import Panel
from rich.progress import MofNCompleteColumn, Progress, SpinnerColumn
from rich.table import Column, Table
from rich.text import Text

from ..utils import batch, flatten, time_in_range
from . import *
from .tele import Client, ClientsSession

logger = logger.bind(scheme="telegram")

CHECKINERS = [
    NebulaCheckin,
    PeachCheckin,
    SingularityCheckin,
    LJYYCheckin,
    TerminusCheckin,
    JMSCheckin,
    BlueseaCheckin,
    EmbyHubCheckin,
]

MONITORERS = [
    # TestMonitor,
    BGKMonitor,
    EmbyhubMonitor,
]

MESSAGERS = [
    # TestMessager,
    NakonakoMessager,
]


def extract(clss):
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
            sender = user.first_name.strip()
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
        client.me.first_name,
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


async def checkin_task(checkiner, sem, wait=0):
    await asyncio.sleep(wait)
    async with sem:
        return await checkiner._start()


async def checkiner(config, instant=False):
    async with ClientsSession.from_config(config) as clients:
        coros = []
        async for tg in clients:
            sem = asyncio.Semaphore(int(config.get("concurrent", 2)))
            checkiners = [
                cls(
                    tg,
                    retries=config.get("retries", 10),
                    timeout=config.get("timeout", 60),
                    nofail=config.get("nofail", True),
                    captcha_service=config.get("captcha_service", 'disabled'),
                    captcha_service_key=config.get("captcha_service_key", 'empty'),
                )
                for cls in extract(CHECKINERS)
            ]
            tasks = []
            for c in checkiners:
                wait = 0 if instant else random.randint(0, 60 * config.get("random", 15))
                task = asyncio.create_task(checkin_task(c, sem, wait))
                tasks.append(task)

            async def _gather_task():
                return tg, await asyncio.gather(*tasks)

            coros.append(_gather_task())
        for f in asyncio.as_completed(coros):
            tg, results = await f
            failed = [c for i, c in enumerate(checkiners) if not results[i]]
            if failed:
                logger.bind(username=tg.me.first_name).error(
                    f"签到失败 ({len(failed)}/{len(checkiners)}): {','.join([f.name for f in failed])}"
                )


async def monitorer(config):
    jobs = []
    async with ClientsSession.from_config(config, monitor=True) as clients:
        async for tg in clients:
            for cls in extract(MONITORERS):
                jobs.append(asyncio.create_task(cls(tg, nofail=config.get("nofail", True))._start()))
        await asyncio.gather(*jobs)


def messager(config, loop, scheduler):
    for account in config.get("telegram", []):
        if account.get("send", False):
            for cls in extract(MESSAGERS):
                cls(
                    account,
                    loop,
                    scheduler,
                    proxy=config.get("proxy", None),
                    nofail=config.get("nofail", True),
                ).start()


async def follower(config):
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
            tg.add_handler(MessageHandler(partial(dump_message, table=table)))
        with Live(table, refresh_per_second=4, vertical_overflow="visible"):
            await asyncio.Event().wait()


async def analyzer(config, chats, keywords, timerange, limit=2000):
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
            target = f"{tg.me.first_name}.msgs"
            logger.info(f'开始分析账号: "{tg.me.first_name}", 结果将写入"{target}".')
            pcs = list(Progress.get_default_columns())
            pcs.insert(0, SpinnerColumn())
            pcs.insert(3, MofNCompleteColumn(table_column=Column(justify="center")))
            p = Progress(*pcs, transient=True)
            with Live(render_page(p, texts)) as live:
                updates = 0
                pchats = p.add_task("[red]会话: ", total=len(chats))
                for c in chats:
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
