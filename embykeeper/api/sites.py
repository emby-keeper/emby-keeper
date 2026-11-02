"""自定义站点 (模板站点) 管理 API.

模板站点以 ``templ_<kind><bot_username>`` 的形式引用, 例如 ``templ_a<moumou_bot>``;
它需要两处配置:

1. 站点列表: ``[site] checkiner = ["templ_a<moumou_bot>"]`` (这里用 ``+`` 前缀追加,
   以便保留默认站点列表);
2. 站点选项: ``[checkiner.'templ_a<moumou_bot>']``.
"""

import ast
import inspect
import textwrap
from datetime import datetime
from collections.abc import Iterable, Mapping, MutableMapping, MutableSet, Sequence, Set
from enum import Enum
from functools import lru_cache
from importlib import import_module
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union, get_args, get_origin

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ValidationError

from .auth import require_auth
from .config import _config_location, _read_config_dict, _write_config_dict
from ..schema import (
    CheckinerConfig,
    Config as CoreConfig,
    MessagerConfig,
    MonitorConfig,
    RegistrarConfig,
    format_errors,
)
from ..telegram.dynamic import get_display_names, get_names, get_spec

router = APIRouter()

SITE_TYPES = ("checkiner", "monitor", "messager", "registrar")

TYPE_LABELS = {
    "checkiner": "签到",
    "monitor": "监控",
    "messager": "水群",
    "registrar": "抢注",
}

TYPE_CONFIG_MODELS = {
    "checkiner": CheckinerConfig,
    "monitor": MonitorConfig,
    "messager": MessagerConfig,
    "registrar": RegistrarConfig,
}

# 任意站点都支持 (见 checkin_main._has_independent_time_range / registrar_main)
UNIVERSAL_OPTIONS = {
    "checkiner": [
        {
            "key": "time_range",
            "type": "str",
            "default": None,
            "description": "该站点单独的签到时段, 设置后将从常规签到中拆出独立执行",
        },
        {"key": "interval_days", "type": "int|str", "default": None, "description": "该站点单独的间隔天数"},
    ],
    # 抢注站点必须配置 times 或 interval_minutes 之一, 否则会被跳过
    "registrar": [
        {
            "key": "times",
            "type": "list",
            "default": None,
            "required": True,
            "description": "定时模式: 每天尝试抢注的时间点, 例如 11:00AM, 11:00PM",
        },
        {
            "key": "interval_minutes",
            "type": "int",
            "default": None,
            "required": True,
            "description": "间隔模式: 每 N 分钟尝试一次, 小于 3 分钟时连续抢注",
        },
        {"key": "retries", "type": "int", "default": 1, "description": "单次抢注的重试次数"},
        {"key": "timeout", "type": "int", "default": 120, "description": "单次抢注的超时时间 (秒)"},
    ],
}

# times / interval_minutes 二选一必填, 用于前端提示
REQUIRED_GROUPS = {
    "registrar": (
        ["times", "interval_minutes"],
        "抢注站点必须配置 times 或 interval_minutes 之一, 否则会被跳过。",
    ),
}

# 内置站点的按站点选项说明 (源码里没有注释时作为补充)
OPTION_DESCRIPTIONS = {
    "time_range": "该站点单独的签到时段, 设置后将从常规签到中拆出独立执行",
    "interval_days": "该站点单独的间隔天数",
    "unique_name": "自动抢注时使用的用户名",
    "possibility": "触发概率 (0~1), 例如 0.7 表示 70% 概率执行",
    "only_history": "仅当在问题历史中找到答案时才自动回答",
    "times": "次数",
    "letters": "字母数量",
    "min_letters": "最少字母数量",
    "max_letters": "最多字母数量",
    "prompt": "使用的提示词",
    "min_interval": "最小发送间隔 (秒)",
    "max_interval": "最大发送间隔 (秒)",
    "interval": "发送间隔 (秒)",
    "at": "需要 @ 的对象",
    "only": "仅在特定条件下发送, 例如 weekends",
    "messages": "使用的语料",
}

OPTION_TYPE_HINTS = {
    "unique_name": "str",
    "possibility": "float",
    "only_history": "bool",
    "messages": "list",
    "message_lists": "str|list",
    "style_messages": "list",
    "style_message_list": "str",
    "chat_name": "int|str",
    "chat_user": "str|list",
    "chat_keyword": "str|list",
    "chat_except_keyword": "str|list",
    "at": "list",
    "min_interval": "int",
    "max_interval": "int",
    "interval": "int",
    "interval_minutes": "int",
    "times": "list",
    "letters": "int",
    "min_letters": "int",
    "max_letters": "int",
    "only": "enum",
    "bot_captcha_char_range": "enum|str",
    "bot_captcha_len": "int|list",
    "checkInHistory": "list",
    "error": "str",
    "success": "bool",
    "id": "int|str",
    "code": "str",
    "tgWebAppData": "str",
    "max_count_recent_5": "int",
    "max_count_recent_10": "int",
    "chat_allow_outgoing": "bool",
    "chat_probability": "float",
    "chat_delay": "int",
    "chat_follow_user": "int",
    "chat_reply": "str|list",
    "allow_edit": "bool",
    "trigger_interval": "int|float",
    "trigger_sim": "int",
    "trigger_max_time": "int|float",
    "allow_caption": "bool",
    "allow_text": "bool",
    "send": "bool",
    "send_immediately": "bool",
    "try_register_bot": "bool",
    "chat_max_length": "int",
    "allow_same_user": "bool",
}

OPTION_CHOICE_HINTS = {
    "only": ["weekday", "weekend"],
    "bot_captcha_char_range": [
        "NUMBER",
        "LLETTER",
        "ULETTER",
        "LLETTER_ULETTER",
        "NUMBER_LLETTER",
        "NUMBER_ULETTER",
        "NUMBER_LLETTER_ULETTER",
        "NOT_NUMBER_LLETTER_ULETTER",
    ],
}

OPTION_CHOICE_VALUE_HINTS = {
    "bot_captcha_char_range": {
        "NUMBER": 0,
        "LLETTER": 1,
        "ULETTER": 2,
        "LLETTER_ULETTER": 3,
        "NUMBER_LLETTER": 4,
        "NUMBER_ULETTER": 5,
        "NUMBER_LLETTER_ULETTER": 6,
        "NOT_NUMBER_LLETTER_ULETTER": 7,
    },
}

TEMPLATE_HINTS = {
    (
        "checkiner",
        "templ_a",
    ): "Sakura_embyboss 面板式机器人: 识别主菜单关键词并点击签到按钮, 支持识别输入式验证码.",
    ("checkiner", "templ_b"): "通用签到机器人: 直接发送签到命令, 支持 OCR 识别验证码.",
    (
        "checkiner",
        "templ_c",
    ): "注册流程模板: 在「签到」调度下尝试注册该机器人, 未开注时按 interval 秒自动重排重试 (相当于定时开注测试).",
    ("monitor", "templ_a"): "自定义监控: 识别到指定关键词后发送通知, 或自动在群组发送信息.",
    ("monitor", "templ_b"): "自定义监控: 多人发送相同消息后自动跟发.",
    ("messager", "templ_a"): "自定义水群: 在指定群组按间隔发送固定消息或消息列表.",
    ("messager", "templ_b"): "自定义水群: 使用 AI 按风格生成消息并发送.",
    (
        "registrar",
        "templ_a",
    ): "注册流程模板: 在「抢注」调度下尝试注册该机器人 (与签到 templ_c 是同一套注册流程, 区别在调度与所属模块; 需高级用户).",
}


class CustomSitePayload(BaseModel):
    type: str
    kind: str = "template"  # template | builtin
    bot: Optional[str] = None
    site: Optional[str] = None
    template: Optional[str] = None
    in_site_list: bool = True
    options: Dict[str, Any] = {}


def _template_module_name(site_type: str, kind: str) -> str:
    sub, _ = get_spec(site_type)
    return f"embykeeper.telegram.{sub}._templ_{kind}"


def _template_module(site_type: str, kind: str):
    try:
        return import_module(_template_module_name(site_type, kind))
    except ImportError as e:
        raise HTTPException(status_code=404, detail=f"模板 {kind} 不存在: {e}")


def _template_kinds(site_type: str) -> List[str]:
    sub, _ = get_spec(site_type)
    module = import_module(f"embykeeper.telegram.{sub}")
    directory = Path(module.__path__[0])
    kinds = []
    for path in sorted(directory.glob("_templ_*.py")):
        kinds.append(path.stem[len("_templ_") :])
    return kinds


# 类型标签的规范原子与固定顺序 (避免出现 str|int / int|Iterable 这类原始注解名)
TYPE_ATOMS = ("bool", "int", "float", "enum", "str", "list", "dict", "any")
LIST_ORIGINS = (list, set, frozenset, tuple, Iterable, Sequence, Set, MutableSet)
DICT_ORIGINS = (dict, Mapping, MutableMapping)


def _annotation_atoms(annotation: Any) -> set:
    """把一个注解拆解为规范原子集合."""
    if annotation is None or annotation is type(None):
        return set()

    origin = get_origin(annotation)
    if origin is Union:
        atoms: set = set()
        for arg in get_args(annotation):
            atoms |= _annotation_atoms(arg)
        return atoms
    if origin is Literal:
        return {"enum"}
    if origin in LIST_ORIGINS:
        return {"list"}
    if origin in DICT_ORIGINS:
        return {"dict"}

    if annotation is Any:
        return {"any"}
    if annotation is bool:
        return {"bool"}
    if annotation is int:
        return {"int"}
    if annotation is float:
        return {"float"}
    if annotation is str:
        return {"str"}

    if isinstance(annotation, type):
        if issubclass(annotation, Enum):
            return {"enum"}
        if issubclass(annotation, bool):
            return {"bool"}
        if issubclass(annotation, int):
            return {"int"}
        if issubclass(annotation, float):
            return {"float"}
        if issubclass(annotation, str):
            return {"str"}
        if issubclass(annotation, (list, tuple, set, frozenset)):
            return {"list"}
        if issubclass(annotation, dict):
            return {"dict"}

    return {"any"}


def _annotation_name(annotation: Any) -> str:
    """把注解归一为规范类型名, 例如 ``Optional[Union[str, int]]`` -> ``int|str``."""
    atoms = _annotation_atoms(annotation)
    if not atoms:
        return "any"
    ordered = [atom for atom in TYPE_ATOMS if atom in atoms]
    if not ordered:
        return "any"
    if len(ordered) > 1:
        ordered = [atom for atom in ordered if atom != "any"] or ["any"]
    return "|".join(ordered)


def _annotation_choices(annotation: Any) -> List[str]:
    """枚举类注解的可选值 (Literal 或 Enum)."""
    origin = get_origin(annotation)
    if origin is Union:
        choices: List[str] = []
        for arg in get_args(annotation):
            for choice in _annotation_choices(arg):
                if choice not in choices:
                    choices.append(choice)
        return choices
    if origin is Literal:
        return [str(value) for value in get_args(annotation)]
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return [member.name for member in annotation]
    return []


def _annotation_choice_values(annotation: Any) -> Dict[str, Any]:
    """Return enum label -> underlying value (Enum names are not runtime values)."""
    origin = get_origin(annotation)
    if origin is Union:
        values: Dict[str, Any] = {}
        for arg in get_args(annotation):
            values.update(_annotation_choice_values(arg))
        return values
    if origin is Literal:
        return {str(value): value for value in get_args(annotation)}
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return {member.name: _jsonable(member.value) for member in annotation}
    return {}


def _field_comments(module) -> Dict[str, str]:
    """从模板模块源码里提取字段的行尾注释作为说明."""
    try:
        source = textwrap.dedent(inspect.getsource(module))
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return {}

    lines = source.splitlines()
    comments: Dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef) or not node.name.endswith("Config"):
            continue
        for statement in node.body:
            if not isinstance(statement, ast.AnnAssign) or not isinstance(statement.target, ast.Name):
                continue
            index = statement.lineno - 1
            if index < 0 or index >= len(lines):
                continue
            line = lines[index]
            if "#" in line:
                comments.setdefault(statement.target.id, line.split("#", 1)[1].strip())
    return comments


def _literal_type(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "str"
    if isinstance(value, (list, tuple)):
        return "list"
    if isinstance(value, dict):
        return "dict"
    return "any"


def _is_config_get(node: ast.Call) -> bool:
    """判断调用是否是 ``config.get(...)`` 或 ``self.config.get(...)``."""
    func = node.func
    if not isinstance(func, ast.Attribute) or func.attr != "get":
        return False
    receiver = func.value
    if isinstance(receiver, ast.Name):
        return receiver.id == "config"
    if isinstance(receiver, ast.Attribute):
        return receiver.attr == "config"
    return False


def _discover_config_options(module) -> List[Dict[str, Any]]:
    """从站点模块源码里找出 ``config.get("key", default)`` 形式的可调项.

    内置站点直接用 ``self.config.get(...)`` 读取按站点配置, 没有 pydantic 模型,
    因此从源码里把这些键、默认值和行尾注释扫出来。
    """
    try:
        source = textwrap.dedent(inspect.getsource(module))
        tree = ast.parse(source)
    except (OSError, SyntaxError):
        return []

    lines = source.splitlines()
    options: Dict[str, Dict[str, Any]] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_config_get(node):
            continue
        if (
            not node.args
            or not isinstance(node.args[0], ast.Constant)
            or not isinstance(node.args[0].value, str)
        ):
            continue

        key = node.args[0].value
        default = None
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            default = node.args[1].value

        index = node.lineno - 1
        comment = ""
        if 0 <= index < len(lines) and "#" in lines[index]:
            comment = lines[index].split("#", 1)[1].strip()

        if key in options:
            if options[key]["default"] is None and default is not None:
                options[key]["default"] = _jsonable(default)
                options[key]["type"] = _literal_type(default)
            if not options[key]["description"] and comment:
                options[key]["description"] = comment
            continue

        options[key] = {
            "key": key,
            "type": OPTION_TYPE_HINTS.get(key, _literal_type(default)),
            "default": _jsonable(default),
            "description": comment or OPTION_DESCRIPTIONS.get(key, ""),
        }
        if key in OPTION_CHOICE_HINTS:
            options[key]["choices"] = OPTION_CHOICE_HINTS[key]
            options[key]["choice_values"] = OPTION_CHOICE_VALUE_HINTS.get(
                key, {choice: choice for choice in OPTION_CHOICE_HINTS[key]}
            )
    return list(options.values())


@lru_cache(maxsize=None)
def _builtin_catalog(site_type: str) -> List[Dict[str, Any]]:
    """列出该类型下所有内置站点及其可调项 (合并基类与通用项)."""
    sub, _ = get_spec(site_type)
    try:
        base_options = _discover_config_options(import_module(f"embykeeper.telegram.{sub}._base"))
    except Exception:
        base_options = []

    universal = UNIVERSAL_OPTIONS.get(site_type, [])
    display_names = get_display_names(site_type)

    catalog = []
    for site in get_names(site_type, allow_ignore=True):
        try:
            module = import_module(f"embykeeper.telegram.{sub}.{site}")
        except Exception:
            continue
        merged: Dict[str, Dict[str, Any]] = {}
        for option in [*base_options, *_discover_config_options(module), *universal]:
            normalized = dict(option)
            key = normalized["key"]
            normalized["type"] = OPTION_TYPE_HINTS.get(key, normalized["type"])
            if key in OPTION_CHOICE_HINTS:
                normalized["choices"] = OPTION_CHOICE_HINTS[key]
                normalized["choice_values"] = OPTION_CHOICE_VALUE_HINTS.get(
                    key, {choice: choice for choice in OPTION_CHOICE_HINTS[key]}
                )
            merged.setdefault(key, normalized)
        catalog.append(
            {
                "site": site,
                "display_name": display_names.get(site, site),
                "options": list(merged.values()),
            }
        )
    return catalog


def _template_config_model(module) -> Optional[type]:
    for name, value in vars(module).items():
        if inspect.isclass(value) and name.endswith("Config") and hasattr(value, "model_fields"):
            return value
    return None


def _template_runtime_class(module) -> Optional[type]:
    for name, value in vars(module).items():
        if inspect.isclass(value) and name.startswith("Template") and not name.endswith("Config"):
            return value
    return None


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    return str(value)


def _template_options(site_type: str, kind: str) -> List[Dict[str, Any]]:
    module = _template_module(site_type, kind)
    model = _template_config_model(module)
    runtime_class = _template_runtime_class(module)
    comments = _field_comments(module)

    options: List[Dict[str, Any]] = []
    seen = set()
    for option in UNIVERSAL_OPTIONS.get(site_type, []):
        options.append(option)
        seen.add(option["key"])

    model_fields = model.model_fields.items() if model is not None else []
    for key, field in model_fields:
        if key in seen:
            continue
        seen.add(key)
        configured_default = None if field.is_required() else _jsonable(field.default)
        runtime_default = getattr(runtime_class, key, None) if runtime_class is not None else None
        effective_default = (
            configured_default if configured_default is not None else _jsonable(runtime_default)
        )
        option: Dict[str, Any] = {
            "key": key,
            "type": _annotation_name(field.annotation),
            "default": configured_default,
            "effective_default": effective_default,
            "description": field.description or comments.get(key, ""),
        }
        choices = _annotation_choices(field.annotation)
        if choices:
            option["choices"] = choices
            option["choice_values"] = _annotation_choice_values(field.annotation)
        options.append(option)

    # Some templates (notably checkiner templ_c) read raw config keys without a Pydantic model.
    if model is None:
        for discovered in _discover_config_options(module):
            if discovered["key"] in seen:
                continue
            seen.add(discovered["key"])
            option = dict(discovered)
            option["type"] = OPTION_TYPE_HINTS.get(option["key"], option["type"])
            if option["key"] in OPTION_CHOICE_HINTS:
                option["choices"] = OPTION_CHOICE_HINTS[option["key"]]
                option["choice_values"] = OPTION_CHOICE_VALUE_HINTS.get(
                    option["key"], {choice: choice for choice in OPTION_CHOICE_HINTS[option["key"]]}
                )
            options.append(option)
    return options


def _template_list(site_type: str) -> List[Dict[str, Any]]:
    templates = []
    for suffix in _template_kinds(site_type):
        kind = f"templ_{suffix}"
        try:
            options = _template_options(site_type, suffix)
        except Exception:
            options = []
        templates.append(
            {
                "kind": kind,
                "hint": TEMPLATE_HINTS.get((site_type, kind), ""),
                "options": options,
            }
        )
    return templates


def _parse_site_name(name: str) -> Optional[Dict[str, str]]:
    """把 ``templ_a<moumou_bot>`` 解析为模板与机器人用户名."""
    raw = name.strip().lstrip("+-")
    if not raw.startswith("templ_") or "<" not in raw or not raw.endswith(">"):
        return None
    kind, _, bot = raw.partition("<")
    bot = bot[:-1].lstrip("@")
    if not kind or not bot:
        return None
    return {"name": raw, "kind": kind, "bot": bot}


def _site_list_entries(raw: Dict[str, Any], site_type: str) -> List[str]:
    site = raw.get("site")
    if not isinstance(site, dict):
        return []
    entries = site.get(site_type)
    if not isinstance(entries, list):
        return []
    return [str(item) for item in entries]


def _custom_sites(raw: Dict[str, Any], site_type: str) -> List[Dict[str, Any]]:
    """列出一个类型下已配置的站点 (自定义模板站点 + 内置站点调整)."""
    items: Dict[str, Dict[str, Any]] = {}
    known_fields = set(TYPE_CONFIG_MODELS[site_type].model_fields.keys())
    display_names = get_display_names(site_type)

    section = raw.get(site_type)
    if isinstance(section, dict):
        for key, value in section.items():
            if key in known_fields or not isinstance(value, dict):
                continue
            parsed = _parse_site_name(key)
            if parsed:
                items[parsed["name"]] = {
                    **parsed,
                    "builtin": False,
                    "options": _jsonable(value),
                    "in_site_list": False,
                }
            else:
                items[key] = {
                    "name": key,
                    "kind": "builtin",
                    "bot": None,
                    "builtin": True,
                    "site": key,
                    "options": _jsonable(value),
                    "in_site_list": True,
                    "display_name": display_names.get(key, key),
                }

    for entry in _site_list_entries(raw, site_type):
        parsed = _parse_site_name(entry)
        if not parsed:
            continue
        existing = items.get(parsed["name"])
        if existing:
            existing["in_site_list"] = not entry.startswith("-")
        else:
            items[parsed["name"]] = {
                **parsed,
                "builtin": False,
                "options": {},
                "in_site_list": not entry.startswith("-"),
            }

    for item in items.values():
        item.setdefault("display_name", str(item["options"].get("name") or item["name"]))
        entries = [
            entry
            for entry in _site_list_entries(raw, site_type)
            if _parse_site_name(entry) and _parse_site_name(entry)["name"] == item["name"]
        ]
        item["site_list_entry"] = next(
            (entry for entry in entries if not entry.startswith("-")), entries[0] if entries else None
        )
        item["list_mode"] = (
            "append"
            if item["site_list_entry"] and item["site_list_entry"].startswith("+")
            else (
                "exclude"
                if item["site_list_entry"] and item["site_list_entry"].startswith("-")
                else "explicit" if item["site_list_entry"] else "not_listed"
            )
        )
    return sorted(items.values(), key=lambda item: item["name"])


def _set_site_list_entry(
    raw: Dict[str, Any], site_type: str, name: str, present: bool, *, remove: bool = False
) -> None:
    site = raw.get("site")
    if not isinstance(site, dict):
        if not present:
            return
        site = {}
        raw["site"] = site

    configured = site.get(site_type)
    current = [str(item) for item in configured] if isinstance(configured, list) else []
    explicit_scope = isinstance(configured, list) and (
        not current or any(not item.startswith(("+", "-")) for item in current)
    )
    matching = [item for item in current if _parse_site_name(item) and _parse_site_name(item)["name"] == name]
    remaining = [item for item in current if item not in matching]

    if present:
        # Editing options must not turn an explicitly-scoped list into "defaults + site".
        existing = next((item for item in matching if not item.startswith("-")), None)
        remaining.append(existing or (name if explicit_scope else f"+{name}"))
    elif not remove:
        # An unchecked site may be explicitly excluded from the default set.
        # Editing its options must not silently remove that exclusion.
        exclusion = next((item for item in matching if item.startswith("-")), None)
        if exclusion:
            remaining.append(exclusion)

    if remaining or explicit_scope:
        site[site_type] = remaining
    else:
        site.pop(site_type, None)

    if not site:
        raw.pop("site", None)


def _save(raw: Dict[str, Any]) -> None:
    model = CoreConfig(**raw)
    _write_config_dict(model.model_dump(mode="json", exclude_none=True, exclude_unset=True))


def _validate_options(
    site_type: str,
    template_suffix: Optional[str],
    options: Dict[str, Any],
) -> Dict[str, Any]:
    """校验选项, 并只保留用户显式填写的项 (避免把默认值写进配置文件)."""
    provided = {key: value for key, value in options.items() if value not in (None, "", [])}
    if not provided or not template_suffix:
        return provided
    module = _template_module(site_type, template_suffix)
    model = _template_config_model(module)
    if model is not None:
        model_options = {key: value for key, value in provided.items() if key in model.model_fields}
        try:
            model.model_validate(model_options)
        except ValidationError as e:
            raise HTTPException(status_code=400, detail=format_errors(e))
    return provided


def _validate_registrar_schedule(options: Dict[str, Any]) -> None:
    times = options.get("times")
    interval = options.get("interval_minutes")

    if times is not None and not isinstance(times, (list, tuple)):
        raise HTTPException(status_code=400, detail="times 必须是时间点列表。")
    if isinstance(times, (list, tuple)) and any(
        not isinstance(item, str) or not item.strip() for item in times
    ):
        raise HTTPException(status_code=400, detail="times 中的每一项都必须是非空时间字符串。")
    for value in times or []:
        for clock_format in ("%H:%M", "%H:%M:%S", "%I:%M%p", "%I:%M %p", "%I%p"):
            try:
                datetime.strptime(value.strip().upper(), clock_format)
                break
            except ValueError:
                continue
        else:
            raise HTTPException(status_code=400, detail=f"无效的抢注时间：{value}。请使用 HH:MM 格式。")
    if interval is not None and (
        not isinstance(interval, int) or isinstance(interval, bool) or interval <= 0
    ):
        raise HTTPException(status_code=400, detail="interval_minutes 必须是大于 0 的整数。")

    has_times = isinstance(times, (list, tuple)) and bool(times)
    has_interval = interval is not None
    if has_times == has_interval:
        raise HTTPException(
            status_code=400,
            detail="活动的抢注站点必须且只能配置一种调度方式：times 或 interval_minutes。",
        )


@router.get("/sites/custom")
async def list_custom_sites(_: bool = Depends(require_auth)):
    """列出各类型的可用模板、可调内置站点与已配置项."""
    try:
        raw = _read_config_dict()
        try:
            model = CoreConfig(**raw)
            defaults = {
                "time_range": (
                    str(model.checkiner.time_range)
                    if model.checkiner and model.checkiner.time_range
                    else None
                ),
                "interval_days": (
                    str(model.checkiner.interval_days)
                    if model.checkiner and model.checkiner.interval_days is not None
                    else None
                ),
            }
        except Exception:
            defaults = {}
        return {
            "types": {
                site_type: {
                    "label": TYPE_LABELS[site_type],
                    "templates": _template_list(site_type),
                    "builtin": _builtin_catalog(site_type),
                    "items": _custom_sites(raw, site_type),
                    "required_group": (
                        {
                            "keys": REQUIRED_GROUPS[site_type][0],
                            "message": REQUIRED_GROUPS[site_type][1],
                        }
                        if site_type in REQUIRED_GROUPS
                        else None
                    ),
                }
                for site_type in SITE_TYPES
            },
            "defaults": defaults,
            "config_file": _config_location(),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"加载自定义站点失败: {e}")


@router.post("/sites/custom")
async def save_custom_site(payload: CustomSitePayload, _: bool = Depends(require_auth)):
    """新增/更新一个模板自定义站点, 或调整一个内置站点的按站点选项."""
    try:
        site_type = payload.type.strip()
        if site_type not in SITE_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的模块: {site_type}")

        kind = payload.kind.strip()
        if kind.startswith("templ_"):
            # 兼容早期只用 kind 传模板名的用法
            payload.template = kind
            kind = "template"

        raw = _read_config_dict()
        section = raw.get(site_type)
        if not isinstance(section, dict):
            section = {}

        if kind == "builtin":
            site = (payload.site or "").strip()
            known = {item["site"] for item in _builtin_catalog(site_type)}
            if site not in known:
                raise HTTPException(status_code=400, detail=f"未知的{TYPE_LABELS[site_type]}站点: {site}")

            name = site
            options = _validate_options(site_type, None, payload.options or {})
            if options:
                section[name] = options
            else:
                section.pop(name, None)
        else:
            template = (payload.template or "").strip()
            if template not in [f"templ_{item}" for item in _template_kinds(site_type)]:
                raise HTTPException(
                    status_code=400, detail=f"{TYPE_LABELS[site_type]} 不支持模板: {template or '(空)'}"
                )

            bot = (payload.bot or "").strip().lstrip("@")
            if not bot or not bot.replace("_", "").isalnum():
                raise HTTPException(status_code=400, detail="机器人用户名只能包含字母、数字和下划线")

            name = f"{template}<{bot}>"
            options = _validate_options(site_type, template[len("templ_") :], payload.options or {})
            if site_type == "registrar" and payload.in_site_list:
                _validate_registrar_schedule(options)
            if options or not payload.in_site_list:
                section[name] = options
            else:
                section.pop(name, None)

            _set_site_list_entry(raw, site_type, name, payload.in_site_list)

        if section:
            raw[site_type] = section
        else:
            raw.pop(site_type, None)

        _save(raw)

        return {"success": True, "name": name, "items": _custom_sites(_read_config_dict(), site_type)}
    except HTTPException:
        raise
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=format_errors(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存自定义站点失败: {e}")


@router.delete("/sites/custom")
async def delete_custom_site(
    type: str = Query(...),
    name: str = Query(...),
    _: bool = Depends(require_auth),
):
    """删除一个自定义站点或一个内置站点的按站点调整."""
    try:
        site_type = type.strip()
        if site_type not in SITE_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的模块: {site_type}")

        parsed = _parse_site_name(name)
        if not parsed:
            site = name.strip()
            if site not in {item["site"] for item in _builtin_catalog(site_type)}:
                raise HTTPException(status_code=400, detail="不是有效的自定义站点名称")

        target = parsed["name"] if parsed else name.strip()

        raw = _read_config_dict()
        section = raw.get(site_type)
        if isinstance(section, dict):
            section.pop(target, None)
            if not section:
                raw.pop(site_type, None)

        if parsed:
            _set_site_list_entry(raw, site_type, target, False, remove=True)
        _save(raw)

        return {"success": True, "items": _custom_sites(_read_config_dict(), site_type)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除自定义站点失败: {e}")
