import asyncio
import csv
from datetime import datetime
from pathlib import Path
import random
import re

from pyrogram.types import Message
from pyrogram.errors import RPCError, MessageIdInvalid

from ...utils import to_iterable, truncate_str
from ..link import Link
from ..lock import pornemby_alert
from ._base import Monitor


class _PornembyAnswerResultMonitor(Monitor):
    name = "Pornemby 问题答案"
    chat_except_keyword = "猜猜是什么番号"
    chat_keyword = r"问题\d*：(.*?)\n+A:(.*)\n+B:(.*)\n+C:(.*)\n+D:(.*)\n+答案为：([ABCD])"
    additional_auth = ["pornemby_pack"]
    allow_edit = True
    allow_caption = False

    key_map = {"A": 1, "B": 2, "C": 3, "D": 4}

    async def on_trigger(self, message: Message, key, reply):
        spec = f"[gray50]({truncate_str(key[0], 10)})[/]"
        self.log.info(f"本题正确答案为 {key[5]} ({key[self.key_map[key[5]]]}): {spec}.")


class _PornembyAnswerAnswerMonitor(Monitor):
    name = "Pornemby 问题回答"
    history_chat_name = "Pornemby"
    chat_user = [
        "pornemby_question_bot",
        "PronembyTGBot2_bot",
        "PronembyTGBot3_bot",
        "PornembyBot",
        "Porn_Emby_Bot",
        "Porn_Emby_Scriptbot",
    ]
    chat_except_keyword = "猜猜是什么番号"
    chat_keyword = r"问题\d*：(.*?)\n+(A:.*\n+B:.*\n+C:.*\n+D:.*)\n(?!\n*答案)"
    additional_auth = ["pornemby_pack"]

    cache = {}
    lock = asyncio.Lock()

    key_map = {
        "A": ["A", "🅰"],
        "B": ["B", "🅱"],
        "C": ["C", "🅲"],
        "D": ["D", "🅳"],
    }

    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self.cache_file = Path(self.basedir) / "pornemby_question.csv"
        self.update_task = None

    async def update_cache(self, to_date=None):
        cache_timestamp = self.cache_file.with_name("pornemby_question.timestamp")
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.cache_file.exists():
            created = True
            to_date = datetime.fromtimestamp(0)
            self.log.info("首次使用 Pornemby 科举, 正在缓存问题答案历史.")
        else:
            created = False
            if cache_timestamp.exists() and not to_date:
                with open(cache_timestamp) as f:
                    try:
                        to_date = datetime.fromtimestamp(float(f.read()))
                    except ValueError:
                        to_date = datetime.fromtimestamp(0)
            else:
                to_date = datetime.fromtimestamp(0)
            self.log.info(f"正在更新问题答案历史缓存.")
            self.log.debug(f"上一次问题答案历史写入于 {to_date.strftime('%Y-%m-%d %H:%M')}.")
        count = 0
        qs = 0
        finished = False
        with open(self.cache_file, mode="a+", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile)
            if created:
                writer.writerow(["Question", "A", "B", "C", "D", "Answer"])
            while not finished:
                finished = True
                m: Message
                for g in to_iterable(self.history_chat_name):
                    async for m in self.client.search_messages(g, limit=100, offset=count, query="答案为"):
                        if m.date < to_date:
                            break
                        count += 1
                        finished = False
                        if m.text:
                            for key in _PornembyAnswerResultMonitor.keys(m):
                                qs += 1
                                writer.writerow(key)
                if count and (finished or count % 500 == 0):
                    self.log.info(f"读取问题答案历史: 已读取 {qs} 问题 / {count} 信息.")
                    await asyncio.sleep(2)
        self.log.debug(f"已向问题答案历史缓存写入 {qs} 条问题.")
        with open(cache_timestamp, "w+", encoding="utf-8") as f:
            f.write(str(datetime.now().timestamp()))

    async def read_cache(self):
        if not self.cache_file.exists():
            return {}
        questions = {}
        with open(self.cache_file, "r", encoding="utf-8") as csvfile:
            rows = csv.DictReader(csvfile)
            for row in rows:
                entry = dict(row)
                questions[entry["Question"]] = entry["Answer"]
        self.log.debug(f"已从问题答案历史缓存读取 {len(questions)} 条问题.")
        return questions

    async def update(self):
        try:
            await asyncio.wait_for(self.lock.acquire(), 1)
        except asyncio.TimeoutError:
            self.log.debug("等待其他协程缓存问题答案历史.")
            async with self.lock:
                return True
        else:
            try:
                await self.update_cache()
                self.__class__.cache = await self.read_cache()
                return True
            finally:
                self.lock.release()

    async def cache_watchdog(self):
        try:
            while True:
                secs = 3600 * 12
                self.log.debug(f"等待 {secs} 秒后进行缓存更新.")
                await asyncio.sleep(secs)
                await self.update()
        except asyncio.CancelledError:
            raise

    async def init(self):
        self.update_task = asyncio.create_task(self.cache_watchdog())
        return await self.update()

    async def on_trigger(self, message: Message, key, reply):
        spec = f"[gray50]({truncate_str(key[0], 10)})[/]"
        if pornemby_alert.get(self.client.me.id, False):
            self.log.info(f"由于风险急停不作答: {spec}.")
            return
        if random.random() > self.config.get("possibility", 1.0):
            self.log.info(f"由于概率设置不作答: {spec}.")
            return
        result = self.cache.get(key[0], None)
        if result:
            self.log.info(f"从缓存回答问题为{result}: {spec}.")
        elif self.config.get("only_history", False):
            self.log.info(f"未从历史缓存找到问题, 请自行回答: {spec}.")
            return
        else:
            question = key[0]
            choices = key[1]
            question = re.sub(r"\([^\)]*From资料库:第\d+题\)", "", question)
            for retries in range(3):
                self.log.debug(f"未从历史缓存找到问题, 开始请求云端问题回答: {spec}.")
                result, by = await Link(self.client).pornemby_answer(question + "\n" + choices)
                if result:
                    self.log.info(f"请求 {by or '云端'} 问题回答为{result}: {spec}.")
                    break
                else:
                    self.log.info(f"云端问题回答错误或超时, 正在重试: {spec}.")
            else:
                self.log.info(f"错误次数超限, 回答失败: {spec}.")
                return
        try:
            await asyncio.sleep(random.uniform(2, 4))
            buttons = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            answer_options = self.key_map[result]
            for button_text in buttons:
                if any((o in button_text) for o in answer_options):
                    try:
                        await message.click(button_text)
                    except (TimeoutError, MessageIdInvalid):
                        pass
                    break
            else:
                self.log.info(f"点击失败: 未找到匹配的按钮文本 {result} {spec}.")
        except KeyError:
            self.log.info(f"点击失败: {result} 不是可用的答案 {spec}.")
        except RPCError:
            self.log.info(f"点击失败: 问题已失效.")


class PornembyAnswerMonitor:
    class PornembyAnswerResultMonitor(_PornembyAnswerResultMonitor):
        chat_name = "Pornemby"

    class PornembyAnswerAnswerMonitor(_PornembyAnswerAnswerMonitor):
        chat_name = "Pornemby"
