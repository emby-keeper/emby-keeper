import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path
import random
import sys
import site
import traceback
from typing import Any, Coroutine, Iterable, Optional, Union

from loguru import logger

from . import var, __url__, __name__, __version__
from .schema import ProxyConfig


def get_path_frame(e, path):
    """获取指定路径下的最后一个错误栈帧.

    Args:
        e: 异常对象
        path: 要搜索的路径

    Returns:
        FrameSummary: 找到的栈帧, 如果未找到则返回 None
    """
    try:
        tb = traceback.extract_tb(e.__traceback__)
        for frame in reversed(tb):
            if Path(path) in Path(frame.filename).parents and frame.name not in ("invoke", "__getattr__"):
                return frame
        else:
            return None
    except AttributeError:
        return None


def get_last_frame(e):
    """获取异常的最后一个栈帧.

    Args:
        e: 异常对象

    Returns:
        FrameSummary: 最后一个栈帧, 如果未找到则返回 None
    """
    try:
        tb = traceback.extract_tb(e.__traceback__)
        for frame in reversed(tb):
            return frame
    except AttributeError:
        return None


def get_cls_fullpath(c):
    """获取类的完整路径名称.

    Args:
        c: 类对象

    Returns:
        str: 类的完整路径名称, 包含模块名
    """
    module = c.__module__
    if module == "builtins":
        return c.__qualname__
    return module + "." + c.__qualname__


def format_exception(e, regular=True):
    """格式化异常信息为可读字符串.

    Args:
        e: 异常对象
        regular: 是否为常规异常 (如网络错误等), 影响不同日志等级下提示信息的格式

    Returns:
        str: 格式化后的异常信息
    """
    if not regular:
        prompt = f"\n请在 Github 或交流群反馈下方错误详情以帮助开发者修复该问题 (当前版本: {__version__}):\n"
    else:
        prompt = ""
    proj_path = Path(__file__).parent.absolute()
    proj_frame = get_path_frame(e, proj_path)
    if proj_frame:
        proj_frame_path = Path(proj_frame.filename).relative_to(proj_path)
        prompt += f"\n  P {proj_frame_path}:{proj_frame.lineno}, F {proj_frame.name}:"
        prompt += f"\n    {proj_frame.line.strip()}"
    last_frame = get_last_frame(e)
    if last_frame:
        last_frame_path = last_frame.filename
        for p in site.getsitepackages():
            if Path(p) in Path(last_frame.filename).parents:
                last_frame_path = "<SP>/" + str(Path(last_frame.filename).relative_to(p))
                break
        prompt += f"\n  S {last_frame_path}:{last_frame.lineno}, F {last_frame.name}:"
        prompt += f"\n    {last_frame.line.strip()}"
    prompt += f"\n    E {get_cls_fullpath(type(e))}: {e}\n"
    return prompt


def show_exception(e, regular=True):
    """显示异常信息.

    Args:
        e: 异常对象
        regular: 是否为常规异常 (如网络错误等), 影响不同日志等级下提示信息的格式
    """
    if (regular and var.debug <= 1) or (not regular and var.debug == 0):
        var.console.rule()
        print(format_exception(e, regular=regular), flush=True, file=sys.stderr)
        var.console.rule()
    else:
        logger.opt(exception=e).debug("错误详情:")


class AsyncTaskPool:
    """一个用于批量等待异步任务的管理器, 支持在等待时添加任务."""

    def __init__(self):
        self.waiter = asyncio.Condition()
        self.tasks = []

    def add(self, coro: Coroutine, name: str = None):
        async def wrapper():
            task = asyncio.ensure_future(coro)
            await asyncio.wait([task])
            async with self.waiter:
                self.waiter.notify()
                return await task

        t = asyncio.create_task(wrapper())
        t.set_name(name or coro.__name__)
        self.tasks.append(t)
        return t

    async def as_completed(self):
        for t in self.tasks:
            if t.done():
                yield t
                self.tasks.remove(t)
        while self.tasks:
            async with self.waiter:
                await self.waiter.wait()
                for t in self.tasks[:]:
                    if t.done():
                        yield t
                        self.tasks.remove(t)

    async def wait(self):
        results = []
        async for t in self.as_completed():
            results.append(t.result())
        return results


class AsyncCountPool(dict):
    """一个异步安全的 ID 分配器.

    Args:
        base: ID 起始数
    """

    def __init__(self, *args, base=1000, **kw):
        super().__init__(*args, **kw)
        self.lock = asyncio.Lock()
        self.next = base + 1

    async def append(self, value):
        """输入一个值, 该值将被存储并分配一个 ID."""
        async with self.lock:
            key = self.next
            self[key] = value
            self.next += 1
            return key


def to_iterable(var: Union[Iterable, Any]):
    """
    将任何变量变为可迭代变量.

    Note:
        None 将变为空数组.
        非可迭代变量将变为仅有该元素的长度为 1 的数组.
        可迭代变量将保持不变.
    """
    if var is None:
        return ()
    if isinstance(var, str) or not isinstance(var, Iterable):
        return (var,)
    else:
        return var


def remove_prefix(text: str, prefix: str):
    """从字符串头部去除前缀."""
    return text[text.startswith(prefix) and len(prefix) :]


def truncate_str(text: str, length: int):
    """将字符串截断到特定长度, 并增加"..."后缀."""
    return f"{text[:length + 3]}..." if len(text) > length else text


def time_in_range(start, end, x):
    """判定时间在特定范围内."""
    if start <= end:
        return start <= x <= end
    else:
        return start <= x or x <= end


def batch(iterable, n=1):
    """将数组分成 N 份."""
    l = len(iterable)
    for ndx in range(0, l, n):
        yield iterable[ndx : min(ndx + n, l)]


def flatten(l):
    """将二维数组变为一维数组."""
    return [item for sublist in l for item in sublist]


def async_partial(f, *args1, **kw1):
    """Partial 函数的异步形式."""

    async def func(*args2, **kw2):
        return await f(*args1, *args2, **kw1, **kw2)

    return func


async def idle():
    """异步无限等待函数."""
    await asyncio.Future()


def random_time(start_time: time = None, end_time: time = None):
    """在特定的开始和结束时间之间生成时间, 如果开始时间晚于结束时间, 视为过夜."""
    start_datetime = datetime.combine(date.today(), start_time or time(0, 0))
    end_datetime = datetime.combine(date.today(), end_time or time(23, 59, 59))
    if end_datetime < start_datetime:
        end_datetime += timedelta(days=1)
    time_diff_seconds = (end_datetime - start_datetime).total_seconds()
    random_seconds = random.randint(0, int(time_diff_seconds))
    random_time = (start_datetime + timedelta(seconds=random_seconds)).time()
    return random_time


def next_random_datetime(start_time: time = None, end_time: time = None, interval_days: int = 1):
    """在特定的开始和结束时间之间生成时间, 并设定最小间隔天数."""
    if interval_days == 0:
        min_datetime = datetime.now()
    else:
        min_date = (datetime.now() + timedelta(days=interval_days)).date()
        min_datetime = datetime.combine(min_date, time(0, 0))
    target_time = random_time(start_time, end_time)
    offset_date = 0
    while True:
        t = datetime.combine(datetime.now() + timedelta(days=offset_date), target_time)
        if t >= min_datetime:
            break
        else:
            offset_date += 1
    return t


def format_timedelta_human(delta: timedelta):
    """将时间差转换为人类可读形式."""
    d = delta.days
    h, s = divmod(delta.seconds, 3600)
    m, s = divmod(s, 60)
    labels = ["天", "小时", "分钟", "秒"]
    dhms = ["%s %s" % (i, lbl) for i, lbl in zip([d, h, m, s], labels)]
    for start in range(len(dhms)):
        if not dhms[start].startswith("0"):
            break
    for end in range(len(dhms) - 1, -1, -1):
        if not dhms[end].startswith("0"):
            break
    parts = dhms[start : end + 1]
    if not parts:
        return "0 秒"
    else:
        return ", ".join(parts)


def format_byte_human(B: float):
    """将字节数转换为人类可读形式."""
    B = float(B)
    KB = float(1024)
    MB = float(KB**2)  # 1,048,576
    GB = float(KB**3)  # 1,073,741,824
    TB = float(KB**4)  # 1,099,511,627,776

    if B < KB:
        return "{0} {1}".format(B, "Bytes" if 0 == B > 1 else "Byte")
    elif KB <= B < MB:
        return "{0:.2f} KB".format(B / KB)
    elif MB <= B < GB:
        return "{0:.2f} MB".format(B / MB)
    elif GB <= B < TB:
        return "{0:.2f} GB".format(B / GB)
    elif TB <= B:
        return "{0:.2f} TB".format(B / TB)


@asynccontextmanager
async def nonblocking(lock: asyncio.Lock):
    """如果锁需要等待释放, 就跳过该部分."""
    try:
        await asyncio.wait_for(lock.acquire(), 0)
    except asyncio.TimeoutError:
        acquired = False
    else:
        acquired = True
    try:
        yield
    finally:
        if acquired:
            lock.release()


@asynccontextmanager
async def optional(lock: Optional[asyncio.Lock]):
    """可选的异步锁, 锁为 None 就直接运行该部分."""
    if lock is None:
        yield
    else:
        async with lock:
            yield


def distribute_numbers(min_value, max_value, num_elements=1, min_distance=0, max_distance=None, base=[]):
    """随机将一定数量的元素分布在最大最小值之间, 同时限定两元素之间的最小距离和最大距离, 生成起始元素由 `base` 定义."""
    if max_value < min_value:
        raise ValueError("invalid value range.")

    if max_distance and max_distance < min_distance:
        raise ValueError("invalid distance range.")

    numbers = sorted(base)
    results = []

    for _ in range(num_elements):
        allowed_range = []
        for i in range(-1, len(numbers)):
            if i == -1:
                min_allowed_value = min_value
            else:
                min_allowed_value = max(numbers[i] + min_distance, min_value)
            if i == len(numbers) - 1:
                max_allowed_value = max_value
            else:
                max_allowed_value = min(numbers[i + 1] - min_distance, max_value)
            if min_allowed_value < max_allowed_value:
                allowed_range.append((min_allowed_value, max_allowed_value))
        if not allowed_range:
            break
        estimated_num_elements = [
            min(int((r[1] - r[0]) // min_distance), num_elements) for r in allowed_range
        ]
        r = random.choices(allowed_range, k=1, weights=estimated_num_elements)[0]
        d = r[1] - r[0]
        min_v = r[0] + min_distance if r[0] == min_value else r[0]
        max_v = r[1]
        if max_distance and d > max_distance:
            value = random.uniform(min_v, r[0] + max_distance - min_distance)
        else:
            value = random.uniform(min_v, max_v)
        numbers = sorted(numbers + [value])
        results.append(value)
    return sorted(results)


def get_proxy_str(proxy: Optional[ProxyConfig] = None):
    """将代理设置转为 URL 形式."""
    if proxy:
        proxy_str = f"{proxy.scheme}://"
        if proxy.username:
            proxy_str += f"{proxy.username or ''}:{proxy.password or ''}@"
        proxy_str += f"{proxy.hostname}:{proxy.port}"
    else:
        proxy_str = None
    return proxy_str


def deep_update(base_dict, update_dict):
    """递归地更新字典"""
    for key, value in update_dict.items():
        if isinstance(value, dict) and key in base_dict and isinstance(base_dict[key], dict):
            deep_update(base_dict[key], value)
        else:
            base_dict[key] = value
    return base_dict


class ProxyBase:
    """
    A proxy class that make accesses just like direct access to __subject__ if not overwriten in the class.
    Attributes defined in class. attrs named in __noproxy__ will not be proxied to __subject__.
    """

    __slots__ = ()

    def __call__(self, *args, **kw):
        return self.__subject__(*args, **kw)

    def hasattr(self, attr):
        try:
            object.__getattribute__(self, attr)
            return True
        except AttributeError:
            return False

    def __getattribute__(self, attr, oga=object.__getattribute__):
        if attr.startswith("__") and attr not in oga(self, "_noproxy"):
            subject = oga(self, "__subject__")
            if attr == "__subject__":
                return subject
            return getattr(subject, attr)
        return oga(self, attr)

    def __getattr__(self, attr, oga=object.__getattribute__):
        if attr == "hasattr" or self.hasattr(attr):
            return oga(self, attr)
        else:
            return getattr(oga(self, "__subject__"), attr)

    @property
    def _noproxy(self, oga=object.__getattribute__):
        import inspect

        base = oga(self, "__class__")
        for cls in inspect.getmro(base):
            if hasattr(cls, "__noproxy__"):
                yield from cls.__noproxy__

    def __setattr__(self, attr, val, osa=object.__setattr__):
        if attr == "__subject__" or attr in self._noproxy:
            return osa(self, attr, val)
        return setattr(self.__subject__, attr, val)

    def __delattr__(self, attr, oda=object.__delattr__):
        if attr == "__subject__" or hasattr(type(self), attr) and not attr.startswith("__"):
            oda(self, attr)
        else:
            delattr(self.__subject__, attr)

    def __bool__(self):
        return bool(self.__subject__)

    def __getitem__(self, arg):
        return self.__subject__[arg]

    def __setitem__(self, arg, val):
        self.__subject__[arg] = val

    def __delitem__(self, arg):
        del self.__subject__[arg]

    def __getslice__(self, i, j):
        return self.__subject__[i:j]

    def __setslice__(self, i, j, val):
        self.__subject__[i:j] = val

    def __delslice__(self, i, j):
        del self.__subject__[i:j]

    def __contains__(self, ob):
        return ob in self.__subject__

    for name in "repr str hash len abs complex int long float iter".split():
        exec("def __%s__(self): return %s(self.__subject__)" % (name, name))

    for name in "cmp", "coerce", "divmod":
        exec("def __%s__(self, ob): return %s(self.__subject__, ob)" % (name, name))

    for name, op in [
        ("lt", "<"),
        ("gt", ">"),
        ("le", "<="),
        ("ge", ">="),
        ("eq", " == "),
        ("ne", "!="),
    ]:
        exec("def __%s__(self, ob): return self.__subject__ %s ob" % (name, op))

    for name, op in [("neg", "-"), ("pos", "+"), ("invert", "~")]:
        exec("def __%s__(self): return %s self.__subject__" % (name, op))

    for name, op in [
        ("or", "|"),
        ("and", "&"),
        ("xor", "^"),
        ("lshift", "<<"),
        ("rshift", ">>"),
        ("add", "+"),
        ("sub", "-"),
        ("mul", "*"),
        ("div", "/"),
        ("mod", "%"),
        ("truediv", "/"),
        ("floordiv", "//"),
    ]:
        exec(
            (
                "def __%(name)s__(self, ob):\n"
                "    return self.__subject__ %(op)s ob\n"
                "\n"
                "def __r%(name)s__(self, ob):\n"
                "    return ob %(op)s self.__subject__\n"
                "\n"
                "def __i%(name)s__(self, ob):\n"
                "    self.__subject__ %(op)s=ob\n"
                "    return self\n"
            )
            % locals()
        )

    del name, op

    def __index__(self):
        return self.__subject__.__index__()

    def __rdivmod__(self, ob):
        return divmod(ob, self.__subject__)

    def __pow__(self, *args):
        return pow(self.__subject__, *args)

    def __ipow__(self, ob):
        self.__subject__ **= ob
        return self

    def __rpow__(self, ob):
        return pow(ob, self.__subject__)


class Proxy(ProxyBase):
    def __init__(self, val):
        self.set(val)

    def set(self, val):
        self.__subject__ = val


class FuncProxy(ProxyBase):
    __noproxy__ = ("_func", "_args", "_kw")

    def __init__(self, func, *args, **kw):
        self._func = func
        self._args = args
        self._kw = kw

    @property
    def __subject__(self):
        return self._func(*self._args, **self._kw)


class CachedFuncProxy(FuncProxy):
    __noproxy__ = ("_cached_value",)

    def __init__(self, func, *args, **kw):
        super().__init__(func, *args, **kw)
        self._cached_value = None

    @property
    def __subject__(self):
        if self._cached_value is None:
            self._cached_value = self._func(*self._args, **self._kw)
        return self._cached_value
