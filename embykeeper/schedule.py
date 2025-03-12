import asyncio
from datetime import datetime, time, timedelta
from dateutil import parser
import re
from typing import Callable, Union
import json
import hashlib

from loguru import logger

from .config import config
from .runinfo import RunContext, RunStatus
from .utils import next_random_datetime


class Scheduler:
    """异步函数计划执行器"""

    @classmethod
    def from_str(
        cls,
        func: Callable,
        interval_days: str,
        time_range: str,
        **kw,
    ):
        """从字符串创建调度器

        Args:
            func: 要执行的异步函数
            interval_days: 间隔天数字符串，支持数字或 "<min,max>" 格式
            time_range: 时间范围字符串，支持具体时间或 "<start,end>" 格式
        Returns:
            Scheduler: 调度器实例
        """
        # Parse interval days
        interval_range_match = re.match(r"<\s*(\d+)\s*,\s*(\d+)\s*>", interval_days)
        if interval_range_match:
            days = [int(interval_range_match.group(1)), int(interval_range_match.group(2))]
        else:
            try:
                days = abs(int(interval_days))
            except ValueError:
                raise ValueError(f"无法解析间隔天数: {interval_days}")

        # Parse time range
        time_range_match = re.match(r"<\s*(.*?)\s*,\s*(.*?)\s*>", time_range)
        if time_range_match:
            start_time, end_time = time_range_match.group(1), time_range_match.group(2)
        else:
            start_time = end_time = time_range

        return cls(
            func,
            days=days,
            start_time=start_time,
            end_time=end_time,
            **kw,
        )

    def __init__(
        self,
        func: Callable,
        days: Union[int, list] = 1,
        start_time: Union[str, time] = None,
        end_time: Union[str, time] = None,
        sid: str = None,
        description: str = None,
        on_next_time: Callable[[datetime], None] = None,
    ):
        """
        Args:
            func: 要执行的异步函数
            days: 执行间隔天数，可以是固定天数或者[最小天数, 最大天数]
            start_time: 执行时间范围起始时间 (可选)
            end_time: 执行时间范围结束时间 (可选)
            sid: 调度器ID, 用于缓存下次执行时间
            description: 调度器描述
            on_next_time: 回调函数，在计算出下一次执行时间时调用
        """
        self.func = func
        if config.debug_cron:
            logger.warning(f"计划任务调试模式下任务开始时间被调整为10秒后: {description}")
            debug_time = (datetime.now() + timedelta(seconds=10)).time()
            self.days = 0
            self.start_time = debug_time
            self.end_time = debug_time
        else:
            self.days = days
            self.start_time = self._parse_time(start_time)
            self.end_time = self._parse_time(end_time)
        self.sid = sid
        self.description = description
        self.on_next_time = on_next_time
        self._cache_key = f"scheduler.{sid}" if sid else None
        self._next_time = None
        self._ctx: RunContext = None

    def _parse_time(self, t):
        if isinstance(t, str):
            return parser.parse(t).time()
        return t

    def _get_scheduler_config(self):
        """获取调度器配置的哈希值"""
        config = {
            "days": self.days,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
        }
        # Convert config to a stable string representation and hash it
        config_str = json.dumps(config, sort_keys=True)
        return hashlib.md5(config_str.encode()).hexdigest()

    @property
    def next_time(self) -> datetime:
        """获取下一次执行时间"""
        if not self._next_time:
            self._next_time = self._get_next_time()
        return self._next_time

    def _get_next_time(self) -> datetime:
        """计算或获取缓存的下一次执行时间"""
        from .cache import cache

        now = datetime.now()
        next_time = None

        # Try to get cached next execution time
        if self._cache_key:
            cached = cache.get(self._cache_key)
            if cached:
                cached_config_hash = cached.get("config_hash")
                cached_time = cached.get("next_time")

                # Check if config hash matches and time hasn't passed
                if (
                    cached_config_hash == self._get_scheduler_config()
                    and cached_time
                    and parser.parse(cached_time) > now
                ):
                    next_time = parser.parse(cached_time)

        # Calculate new next_time if needed
        if not next_time:
            # Calculate interval days
            if isinstance(self.days, (list, tuple)):
                interval = self.days[0] + (self.days[1] - self.days[0])
            else:
                interval = self.days

            next_time = next_random_datetime(
                start_time=self.start_time, end_time=self.end_time, interval_days=interval
            )

            # Cache the next execution time with config hash
            if self._cache_key:
                cache.set(
                    self._cache_key,
                    {
                        "config_hash": self._get_scheduler_config(),
                        "next_time": next_time.isoformat(),
                        "description": self.description,
                    },
                )

        return next_time

    async def schedule(self):
        """等待到指定时间范围内执行函数"""
        from .cache import cache

        while True:
            now = datetime.now()
            self._next_time = self._get_next_time()

            # Call the hook function if provided
            if self.on_next_time:
                self._ctx = self.on_next_time(self._next_time)

            # Wait until the scheduled time
            wait_seconds = (self._next_time - now).total_seconds()
            if wait_seconds > 0:
                await asyncio.sleep(wait_seconds)

            # Execute the function
            try:
                try:
                    # Shield the function execution to distinguish cancellation source
                    await asyncio.shield(self.func(self._ctx))
                except asyncio.CancelledError:
                    # This is a cancellation from within self.func
                    if self._ctx:
                        self._ctx.finish(RunStatus.ERROR, "任务在运行时被取消")
                    raise  # Re-raise to be caught by outer try block
            except asyncio.CancelledError:
                # This is a cancellation from outside schedule()
                if self._ctx:
                    self._ctx.finish(RunStatus.CANCELLED, "任务被取消")
                raise  # Re-raise to propagate cancellation
            except Exception:
                if self._ctx:
                    self._ctx.finish(RunStatus.ERROR, f"任务发生错误")
                if not config.nofail:
                    raise

            if self._cache_key:
                try:
                    cache.delete(self._cache_key)
                except KeyError:
                    pass
            self._ctx = None
            self._next_time = None

            # If days is 0, break the loop after one execution
            if isinstance(self.days, (list, tuple)) and self.days[0] == 0:
                break
