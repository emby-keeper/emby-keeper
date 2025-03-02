from __future__ import annotations

from asyncio import Event
import asyncio
from datetime import datetime
from enum import IntEnum, auto
from typing import TYPE_CHECKING, Callable, Dict, List
import random
import string
from loguru import logger

from rich.text import Text
from pydantic import BaseModel, PrivateAttr

from .utils import to_iterable
from .cache import cache

if TYPE_CHECKING:
    from loguru import Logger

_running_runs: Dict[str, RunContext] = {}


class RunStatus(IntEnum):
    CATAGORY = auto()
    PENDING = auto()
    INITIALIZING = auto()
    RUNNING = auto()
    SUCCESS = auto()
    NONEED = auto()
    FAIL = auto()
    CANCELLED = auto()
    ERROR = auto()
    SKIP = auto()
    IGNORE = auto()
    RESCHEDULE = auto()


class LogRecord(BaseModel):
    level: str
    message: str
    time: datetime


class RunContext(BaseModel):
    _finished: Event = PrivateAttr(default_factory=Event)
    _started: Event = PrivateAttr(default_factory=Event)
    _cancel: Callable = PrivateAttr(default=None)
    _handler_id: int = PrivateAttr(default=None)

    id: str
    parent_ids: List[str] = []
    description: str = None
    status: RunStatus = RunStatus.PENDING
    status_info: str = None
    log: List[LogRecord] = []
    duration: float = None
    start_time: datetime = None
    end_time: datetime = None
    next_time: datetime = None
    reschedule: int = None

    def start(self, status: RunStatus = RunStatus.RUNNING):
        """开始任务，设置开始时间和状态"""
        self.start_time = datetime.now()
        self.set(status)
        self._started.set()

    def set(self, status: RunStatus = None):
        """设置状态"""

        if status:
            self.status = status
            self.log.append(
                LogRecord(level="DEBUG", message=f"任务状态已设置为 {status.name}", time=datetime.now())
            )

    def finish(self, status: RunStatus = None, status_info: str = None):
        """完成任务，记录状态和时间，并保存到缓存"""

        # 设置结束状态
        self.set(status)
        if status_info:
            self.status_info = status_info
        self.end_time = datetime.now()

        # 计算持续时间
        if self.start_time:
            self.duration = (self.end_time - self.start_time).total_seconds()

        # 从运行中任务列表移除
        if self.id in _running_runs:
            del _running_runs[self.id]

        # 设置完成事件
        self._finished.set()

        # 移除logger handler
        if self._handler_id is not None:
            try:
                logger.remove(self._handler_id)
            except ValueError:
                pass

        # 保存到缓存
        self.save()

        return self

    def save(self):
        """保存当前任务到缓存"""
        cache.set(f"runinfo.{self.id}", self.model_dump_json())

    @classmethod
    def cancel_all(cls):
        """取消所有运行中的任务"""
        for run in list(_running_runs.values()):
            run.cancel_tree()
            if run.status != RunStatus.CATAGORY:
                run.finish(RunStatus.CANCELLED, "任务被取消")

    def bind_logger(self, logger: Logger):
        """将 loguru logger 绑定到当前任务"""
        return logger.bind(run_id=self.id)

    @classmethod
    def prepare(cls, description: str = None, parent_ids: List[str] = None):
        """生成一个新的任务上下文"""

        # 生成随机6位ID (大写字母和数字) 的运行时
        chars = string.ascii_uppercase + string.digits
        run_id = "".join(random.choices(chars, k=6))
        run = cls(id=run_id, parent_ids=to_iterable(parent_ids))
        run.description = description

        # 设置对 loguru 的监控
        def log_sink(message):
            record = message.record
            if record["extra"].get("run_id") == run_id:
                log_record = LogRecord(
                    level=record["level"].name.upper(),
                    message=record["message"],
                    time=record["time"],
                )
                run.log.append(log_record)

        # 添加日志处理器
        run._handler_id = logger.add(log_sink, filter=lambda record: "run_id" in record["extra"])

        # 添加到运行中任务列表
        _running_runs[run_id] = run

        # 如果有父任务，记录父子关系
        if parent_ids:
            for parent_id in parent_ids:
                children = cache.get(f"runinfo.children.{parent_id}", [])
                if run_id not in children:
                    children.append(run_id)
                    cache.set(f"runinfo.children.{parent_id}", children)

        return run

    @classmethod
    def get(cls, run_id: str) -> "RunContext":
        # 优先从运行中任务获取
        if run_id in _running_runs:
            return _running_runs[run_id]

        # 从缓存加载
        run_json = cache.get(f"runinfo.{run_id}")
        if run_json:
            return cls.model_validate_json(run_json)
        return None

    def get_parents(self):
        """获取所有父任务"""
        parents = []
        for parent_id in self.parent_ids:
            parent = RunContext.get(parent_id)
            if parent:
                parents.append(parent)
        return parents

    def get_children(self):
        """获取所有子任务"""
        children = []
        child_ids = cache.get(f"runinfo.children.{self.id}", [])
        for child_id in child_ids:
            child = RunContext.get(child_id)
            if child:
                children.append(child)
        return children

    def yield_logs(self, reverse: bool = False, include_children: bool = False):
        """按时间顺序产出日志记录"""
        logs = self.log.copy()

        if include_children:
            for child in self.get_children():
                logs.extend(child.log)

        # 确保所有日志都有时间戳
        for log in logs:
            if log.time is None:
                log.time = datetime.now()

        # 按时间排序
        logs.sort(key=lambda x: x.time, reverse=reverse)
        yield from logs

    def log_sink(self, message):
        record = message.record
        if record["extra"].get("run_id") == self.id:
            log_record = LogRecord(
                level=record["level"].name.upper(),
                message=Text(record["message"]).plain,
                time=record["time"],
            )
            self.log.append(log_record)

    @classmethod
    def run(cls, func: Callable, description: str = None, parent_ids: List[str] = None):
        async def runner():
            ctx = RunContext.prepare(
                description=description or func.__name__,
                parent_ids=parent_ids,
            )
            task = asyncio.create_task(func(ctx))
            ctx._cancel = task.cancel
            try:
                return await task
            except asyncio.CancelledError:
                ctx.finish(RunStatus.CANCELLED, "任务被取消")
                raise
            except Exception as e:
                ctx.finish(RunStatus.ERROR, f"任务发生错误")
                raise

        return runner()

    def get_running_children(self):
        """获取所有正在运行的子任务"""
        children = []
        child_ids = cache.get(f"runinfo.children.{self.id}", [])
        for child_id in child_ids:
            if child_id in _running_runs:
                children.append(_running_runs[child_id])
        return children

    def cancel_tree(self):
        """取消当前任务及其所有运行中的子任务"""
        # 先取消所有子任务
        for child in self.get_running_children():
            if child._cancel:
                child._cancel()

        # 取消自身任务
        if self._cancel:
            self._cancel()

    @classmethod
    def get_or_create(
        cls,
        run_id: str = None,
        description: str = None,
        parent_ids: List[str] = None,
        status: RunStatus = RunStatus.CATAGORY,
    ):
        """获取现有任务或创建新任务"""

        if run_id:
            existing = cls.get(run_id)
            if existing:
                return existing
        ctx = cls.prepare(description=description, parent_ids=parent_ids)
        if status:
            ctx.set(status)
        return ctx
