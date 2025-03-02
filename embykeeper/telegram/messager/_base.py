import asyncio
import random
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Iterable, List, Optional, Union

import yaml
from dateutil import parser
from loguru import logger
from pyrogram.types import User
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChatWriteForbidden, RPCError, SlowmodeWait
from pydantic import BaseModel, Field, ValidationError

from embykeeper import __name__ as __product__
from embykeeper.data import get_data
from embykeeper.var import debug
from embykeeper.utils import show_exception, truncate_str, distribute_numbers
from embykeeper.runinfo import RunContext, RunStatus
from embykeeper.config import config
from embykeeper.schema import TelegramAccount

from ..session import ClientsSession
from ..link import Link

__ignore__ = True


@dataclass(eq=False)
class _MessageSchedule:
    """定义一个发送规划, 即在特定时间段内某些消息中的一个有一定几率被发送."""

    messages: Iterable[str]
    at: Union[Iterable[Union[str, time]], Union[str, time]] = ("0:00", "23:59")
    possibility: float = 1.0
    multiply: int = 1
    only: str = None


@dataclass(eq=False)
class MessageSchedule:
    """定义一个发送规划, 即在特定时间段内某些消息中的一个有一定几率被发送, 允许使用一个话术列表资源名作为基础配置."""

    spec: str = None
    messages: Iterable[str] = None
    at: Union[Iterable[Union[str, time]], Union[str, time]] = None
    possibility: float = None
    only: str = None
    multiply: int = None

    def to_message_schedule(self) -> _MessageSchedule:
        return _MessageSchedule(
            messages=self.messages,
            at=self.at or ("0:00", "23:59"),
            possibility=self.possibility or 1,
            multiply=self.multiply or 1,
            only=self.only,
        )


@dataclass(eq=False)
class MessagePlan:
    """定义一个发送计划, 即在某事件发送某个消息."""

    message: str
    at: datetime
    schedule: _MessageSchedule
    skip: bool = False


class MessageMaterialSchema(BaseModel):
    """语料文件 Schema"""

    messages: List[str]
    at: List[str] = Field(default=["9:00", "23:00"])
    possibility: Optional[float] = Field(default=1.0)
    only: Optional[str] = Field(default=None)


class Messager:
    """自动水群类."""

    name: str = None  # 水群器名称
    chat_name: str = None  # 群聊的名称
    default_messages: List[Union[str, MessageSchedule]] = []  # 默认的话术列表资源名
    additional_auth: List[str] = []  # 额外认证要求
    min_interval: int = None  # 预设两条消息间的最小间隔时间
    max_interval: int = None  # 预设两条消息间的最大间隔时间

    site_last_message_time = None
    site_lock = asyncio.Lock()

    def __init__(
        self,
        account: TelegramAccount,
        context: RunContext = None,
        me: User = None,
        config: dict = None,
    ):
        """
        自动水群类.
        参数:
            account: 账号登录信息
            context: 运行时上下文
            me: 当前用户
            config: 当前水群器的特定配置
        """
        self.account = account
        self.ctx = context or RunContext.prepare()
        self.config = config or {}
        self.me = me
        self.min_interval = config.get(
            "min_interval",
            config.get("interval", self.min_interval or 60),
        )  # 两条消息间的最小间隔时间
        self.max_interval = config.get("max_interval", self.max_interval)  # 两条消息间的最大间隔时间
        self.log = logger.bind(scheme="telemessager", name=self.name, username=me.name)
        self.timeline: List[MessagePlan] = []  # 消息计划序列

    def parse_message_yaml(self, file):
        """解析话术文件."""
        with open(file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        material = MessageMaterialSchema.model_validate(data)

        at = material.at
        assert len(at) == 2
        at = [parser.parse(t).time() for t in at]
        return _MessageSchedule(
            messages=material.messages,
            at=at,
            possibility=material.possibility,
            only=material.only,
        )

    def add(self, schedule: _MessageSchedule, use_multiply=False):
        """根据规划, 生成计划, 并增加到时间线."""
        start_time, end_time = schedule.at
        if isinstance(start_time, str):
            start_time = parser.parse(start_time).time()
        if isinstance(end_time, str):
            end_time = parser.parse(end_time).time()
        start_datetime = datetime.combine(date.today(), start_time or time(0, 0))
        end_datetime = datetime.combine(date.today(), end_time or time(23, 59, 59))
        if end_datetime < start_datetime:
            end_datetime += timedelta(days=1)
        start_timestamp = start_datetime.timestamp()
        end_timestamp = end_datetime.timestamp()
        num_plans = schedule.multiply if use_multiply else 1
        base = [mp.at.timestamp() for mp in self.timeline]
        timestamps = distribute_numbers(
            start_timestamp, end_timestamp, num_plans, self.min_interval, self.max_interval, base=base
        )
        mps = []
        ignored = num_plans - len(timestamps)
        if ignored:
            self.log.warning(f"发生错误: 部分发送计划 ({ignored}) 无法排入当日日程并被跳过, 请检查您的配置.")
            for _ in range(ignored):
                mps.append(
                    MessagePlan(
                        message=random.choice(schedule.messages),
                        at=end_datetime,
                        schedule=schedule,
                        skip=True,
                    )
                )
        for t in timestamps:
            at = datetime.fromtimestamp(t)
            if at < datetime.now():
                at += timedelta(days=1)
            skip = False
            if random.random() >= schedule.possibility:
                skip = True
            elif schedule.only:
                today = datetime.today()
                if schedule.only.startswith("weekday") and today.weekday() > 4:
                    skip = True
                if schedule.only.startswith("weekend") and today.weekday() < 5:
                    skip = True
            mps.append(
                MessagePlan(
                    message=random.choice(schedule.messages),
                    at=at,
                    schedule=schedule,
                    skip=skip,
                )
            )
        self.timeline.extend(mps)
        self.timeline = sorted(self.timeline, key=lambda x: x.at)
        return True

    async def get_spec_path(self, spec):
        """下载话术文件对应的本地或云端文件."""
        if not Path(spec).exists():
            return await get_data(spec, caller=f"{self.name}水群")
        else:
            return spec

    async def get_spec_schedule(self, spec_or_schedule):
        """解析话术文件对应的本地或云端文件."""
        if isinstance(spec_or_schedule, MessageSchedule):
            if spec_or_schedule.spec:
                file = await self.get_spec_path(spec_or_schedule.spec)
                if not file:
                    self.log.warning(f'话术文件 "{spec_or_schedule.spec}" 无法下载或不存在, 将被跳过.')
                    return None
                try:
                    base_schedule = self.parse_message_yaml(file)
                    # Merge base_schedule with spec_or_schedule
                    return _MessageSchedule(
                        messages=spec_or_schedule.messages or base_schedule.messages,
                        at=spec_or_schedule.at or base_schedule.at,
                        possibility=spec_or_schedule.possibility or base_schedule.possibility,
                        multiply=spec_or_schedule.multiply or base_schedule.multiply,
                        only=spec_or_schedule.only or base_schedule.only,
                    )
                except (OSError, yaml.YAMLError, ValidationError) as e:
                    self.log.warning(f'话术文件 "{spec_or_schedule.spec}" 错误, 将被跳过: {e}')
                    show_exception(e)
                    return None
            else:
                return spec_or_schedule.to_message_schedule()
        else:
            file = await self.get_spec_path(spec_or_schedule)
            if not file:
                self.log.warning(f'话术文件 "{spec_or_schedule}" 无法下载或不存在, 将被跳过.')
                return None
            try:
                return self.parse_message_yaml(file)
            except (OSError, yaml.YAMLError, ValidationError) as e:
                self.log.warning(f'话术文件 "{spec_or_schedule}" 错误, 将被跳过: {e}')
                show_exception(e)
                return None

    async def _start(self):
        """自动水群器的入口函数的错误处理外壳."""
        try:
            return await self.start()
        except Exception as e:
            if config.nofail:
                self.log.warning(f"发生错误, 自动水群器将停止.")
                show_exception(e, regular=False)
                return self.ctx.finish(RunStatus.FAIL, "异常错误")
            else:
                raise

    async def start(self):
        """自动水群器的入口函数."""
        self.ctx.start(RunStatus.INITIALIZING)

        if self.additional_auth:
            async with ClientsSession([self.account]) as clients:
                async for _, tg in clients:
                    for a in self.additional_auth:
                        if not await Link(tg).auth(a, log_func=self.log.info):
                            return False

        if self.max_interval and self.min_interval > self.max_interval:
            self.log.warning(f"发生错误: 最小间隔不应大于最大间隔, 自动水群将停止.")
            return False

        if not await self.init():
            self.log.warning(f"状态初始化失败, 自动水群将停止.")
            return False

        messages = self.config.get("messages", [])
        if not messages:
            messages = self.default_messages

        schedules = []
        for m in messages:
            if isinstance(m, MessageSchedule):
                schedule = await self.get_spec_schedule(m)
                if schedule:
                    schedules.append(schedule)
            else:
                match = re.match(r"(.*)\*\s?(\d+)", m)
                if match:
                    multiply = int(match.group(2))
                    spec = match.group(1).strip()
                else:
                    multiply = 1
                    spec = m
                schedule = await self.get_spec_schedule(spec)
                if schedule:
                    schedule.multiply = multiply
                    schedules.append(schedule)

        nmsgs = sum([s.multiply for s in schedules])
        self.log.info(f"共启用 {len(schedules)} 个消息规划, 发送 {nmsgs} 条消息.")
        for s in schedules:
            self.add(s, use_multiply=True)

        self.ctx.status = RunStatus.RUNNING
        if self.timeline:
            last_valid_p = None
            while True:
                valid_p = [p for p in self.timeline if not p.skip]
                self.log.debug(f"时间线上当前有 {len(self.timeline)} 个消息计划, {len(valid_p)} 个有效.")
                if debug > 1:
                    self.log.debug(
                        "时间序列: "
                        + " ".join([p.at.strftime("%d%H%M%S") for p in sorted(valid_p, key=lambda x: x.at)])
                    )
                if valid_p:
                    next_valid_p = min(valid_p, key=lambda x: x.at)
                    if not next_valid_p == last_valid_p:
                        last_valid_p = next_valid_p
                        self.log.info(
                            f"下一次发送将在 [blue]{next_valid_p.at.strftime('%m-%d %H:%M:%S')}[/] 进行: {truncate_str(next_valid_p.message, 20)}."
                        )
                else:
                    self.log.info(f"下一次发送被跳过.")
                next_p = min(self.timeline, key=lambda x: x.at)
                self.log.debug(
                    f"下一次计划任务将在 [blue]{next_p.at.strftime('%m-%d %H:%M:%S')}[/] 进行 ({'跳过' if next_p.skip else '有效'})."
                )
                await asyncio.sleep((next_p.at - datetime.now()).total_seconds())
                if not next_p.skip:
                    await self.send(next_p.message)
                self.timeline.remove(next_p)
                self.add(next_p.schedule)

    async def init(self):
        """可重写的初始化函数, 返回 False 将视为初始化错误."""
        return True

    async def send(self, message):
        """自动水群器的发信器的入口函数."""
        if self.site_last_message_time:
            need_sec = random.randint(5, 10)
            while self.site_last_message_time > datetime.now() - timedelta(seconds=need_sec):
                await asyncio.sleep(1)
        async with ClientsSession([self.account]) as clients:
            async for _, tg in clients:
                chat = await tg.get_chat(self.chat_name)
                self.log.bind(username=tg.me.name).info(f'向聊天 "{chat.name}" 发送: [gray50]{message}[/]')
                try:
                    msg = await tg.send_message(self.chat_name, message)
                except ChatWriteForbidden as e:
                    try:
                        chat = await tg.get_chat(self.chat_name)
                        member = await chat.get_member(tg.me.id)
                        if member.status == ChatMemberStatus.RESTRICTED:
                            if member.until_date:
                                delta = member.until_date - datetime.now()
                                secs = delta.total_seconds()
                                if secs < 2592000:
                                    self.log.warning(f"发送失败: 您已被禁言 {secs} 秒.")
                                else:
                                    self.log.warning(f"发送失败: 您已被永久禁言.")
                            else:
                                self.log.warning(f"发送失败: 您已被禁言.")
                        else:
                            self.log.warning(f"发送失败: 已全员禁言.")
                    except RPCError:
                        self.log.warning(f"发送失败: {e}.")
                except SlowmodeWait as e:
                    self.log.info(f"发送等待: Telegram 限制, 等待 {e.value} 秒.")
                except RPCError as e:
                    self.log.warning(f"发送失败: {e}.")
                except KeyError as e:
                    self.log.warning(f"发送失败, 您可能已被封禁.")
                    show_exception(e)
                except Exception as e:
                    self.log.warning(f"发送失败: {e}.")
                else:
                    async with self.site_lock:
                        self.__class__.site_last_message_time = datetime.now()
                    return msg
