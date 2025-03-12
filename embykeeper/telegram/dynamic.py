from __future__ import annotations

import inspect
import pkgutil
import re
from functools import lru_cache
from importlib import import_module
from typing import List, Type

from loguru import logger

from embykeeper.utils import to_iterable

from . import __name__ as __telechecker__

logger = logger.bind(scheme="telegram")


def get_spec(type: str) -> tuple[str, str]:
    """模块路径解析映射."""
    if type == "checkiner":
        sub = "checkiner"
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


@lru_cache
def get_names(type: str, allow_ignore=False) -> List[str]:
    """列出服务中所有可用站点."""
    sub, _ = get_spec(type)
    results = []
    typemodule = import_module(f"{__telechecker__}.{sub}")
    for _, mn, _ in pkgutil.iter_modules(typemodule.__path__):
        module = import_module(f"{__telechecker__}.{sub}.{mn}")
        if not allow_ignore:
            if not getattr(module, "__ignore__", False):
                results.append(mn)
        else:
            if (not mn.startswith("_")) and (not mn.startswith("test")):
                results.append(mn)
    return results


def get_cls(type: str, names: List[str] = None) -> List[Type]:
    """获得服务特定站点的所有类."""

    sub, suffix = get_spec(type)
    if names == None:
        names = get_names(type)
    else:
        names = to_iterable(names)

    exclude_names = set(name[1:] for name in names if name.startswith("-"))
    include_names = set(name[1:] for name in names if name.startswith("+"))
    names = set(name for name in names if not name.startswith("-") and not name.startswith("+"))

    if not names and (exclude_names or include_names):
        names = set(get_names(type))

    if "all" in names:
        names = set(get_names(type, allow_ignore=True))

    if type == "checkiner":
        if "sgk" in names:
            sgk_names = set(n for n in get_names(type, allow_ignore=True) if n.endswith("sgk"))
            names.update(sgk_names)
            names.remove("sgk")

        if "sgk" in exclude_names:
            sgk_names = set(n for n in names if n.endswith("sgk"))
            names -= sgk_names
            exclude_names.remove("sgk")

        if "sgk" in include_names:
            sgk_names = set(n for n in get_names(type, allow_ignore=True) if n.endswith("sgk"))
            include_names.update(sgk_names)
            include_names.remove("sgk")

    # Apply exclusions
    names = names - exclude_names
    # Add inclusions
    names = list(names | include_names)

    results = []
    for name in names:
        match = re.match(r"templ_(\w+)<(\w+)>", name)
        if match:
            try:
                module = import_module(f"{__telechecker__}.{sub}._templ_{match.group(1).lower()}")
                func = getattr(module, "use", None)
                if not func:
                    logger.warning(f'您配置的 "{type}" 不支持模板 "{match.group(1).upper()}".')
                    continue
                if type == "checkiner":
                    results.append(
                        func(bot_username=match.group(2), name=f"@{match.group(2)}", templ_name=name)
                    )
                elif type == "monitor":
                    results.append(func(name=f"{match.group(2)}", templ_name=name))
                elif type == "messager":
                    results.append(func(chat_name=match.group(2), name=f"@{match.group(2)}", templ_name=name))
            except ImportError:
                all_names = get_names(type)
                logger.warning(f'您配置的 "{type}" 不支持站点 "{name}", 请从以下站点中选择:')
                logger.warning(", ".join(all_names))
        else:
            try:
                module = import_module(f"{__telechecker__}.{sub}.{name.lower()}")
                found_valid_class = False
                expected_name = name.replace("_old", "").replace("_", "")
                for cn, cls in inspect.getmembers(module, inspect.isclass):
                    if (expected_name + suffix).lower() == cn.lower():
                        results.append(cls)
                        found_valid_class = True
                if not found_valid_class:
                    logger.warning(
                        f'您设定了站点 "{name}", 但对应的模块 "{name}" 中未找到合法的类, '
                        f'类名应以 "{expected_name.capitalize() + suffix.capitalize()}" 开头.'
                    )
            except ImportError:
                all_names = get_names(type)
                logger.warning(f'您配置的 "{type}" 不支持站点 "{name}", 请从以下站点中选择:')
                logger.warning(", ".join(all_names))
    return results


def extract(clss: List[Type]) -> List[Type]:
    """对于嵌套类, 展开所有子类."""
    extracted = []
    for cls in clss:
        ncs = [c for c in cls.__dict__.values() if inspect.isclass(c)]
        if ncs:
            extracted.extend(ncs)
        else:
            extracted.append(cls)
    return extracted
