from rich.prompt import Prompt

from .cache import cache
from .var import console


def get_cache_options():
    """获取缓存清理选项"""
    return {
        "1": {"name": "除凭据外所有缓存", "special": "all_except_credentials"},
        "2": {"name": "Emby 模拟设备信息", "prefix": "emby.env"},
        "3": {
            "name": "运行任务日志记录信息",
            "prefix": "runinfo",
            "extra_delete": lambda key: f"runinfo.children.{key.split('.')[-1]}",
        },
        "4": {"name": "下次运行时间缓存", "prefix": "scheduler"},
        "5": {"name": "Emby 登陆凭据", "prefix": "emby.credential", "show_keys": True},
        "6": {"name": "Telegram 登陆凭据", "prefix": "telegram.session_str", "show_keys": True},
        "7": {
            "name": "其他缓存",
            "children": {
                "7.1": {"name": "monitor.pornemby.answer.qa", "prefix": "monitor.pornemby.answer.qa"}
            },
        },
    }


def clean_cache(cache_key: str = None, cache_prefix: str = None):
    """清理指定的缓存

    Args:
        cache_key: 具体的缓存键
        cache_prefix: 缓存前缀
    """
    if cache_key:
        # 清理单个缓存键
        cache.delete(cache_key)
        return f"已清理缓存 {cache_key}"

    if cache_prefix is not None:
        # 清理指定前缀的所有缓存
        if cache_prefix == "all_except_credentials":
            # 特殊处理：清理除凭据外所有缓存
            credential_prefixes = ["emby.credential", "telegram.session_str"]
            all_keys = cache.find_by_prefix("")
            keys_to_delete = [k for k in all_keys if not any(k.startswith(p) for p in credential_prefixes)]
            count = len(keys_to_delete)
            cache.delete_many(keys_to_delete)
            return f"已清理除凭据外所有缓存，共 {count} 条"
        else:
            # 常规前缀清理
            keys = cache.find_by_prefix(cache_prefix)
            count = len(keys)
            cache.delete_many(keys)
            return f"已清理前缀为 {cache_prefix} 的缓存，共 {count} 条"

    return "请指定要清理的缓存键或前缀"


async def cleaner():
    options = get_cache_options()
    console.rule("缓存文件清理")
    console.print("可用的清理选项：")

    for key, option in options.items():
        if "prefix" in option:
            keys = list(cache.find_by_prefix(option["prefix"]))
            count = len(keys)
            if option.get("show_keys", False):
                # 显示凭据类型，需要显示具体的key
                console.print(f"{key}. {option['name']} ({option['prefix']})")
                for i, key_name in enumerate(keys, 1):
                    console.print(f"  {key}.{i}. {key_name}")
            else:
                # 显示普通缓存类型，显示总数
                console.print(f"{key}. {option['name']} (共 {count} 条)")
        elif "children" in option:
            # 显示父选项（如"其他缓存"）
            console.print(f"{key}. {option['name']}")
            for child_key, child in option["children"].items():
                keys = list(cache.find_by_prefix(child["prefix"]))
                count = len(keys)
                # 显示子选项
                console.print(f"  {child_key}. {child['name']} (共 {count} 条)")
                for i, key_name in enumerate(keys, 1):
                    console.print(f"    {child_key}.{i}. {key_name}")
        else:
            # 特殊选项（如"除凭据外所有缓存"）
            console.print(f"{key}. {option['name']}")

    console.rule()
    option = Prompt.ask("\n请输入要清理的选项编号")

    # 根据选项获取实际的缓存键或前缀
    parts = option.split(".", 1)
    parent_key = parts[0]

    if parent_key not in options:
        result = f"无效的选项: {parent_key}"
    else:
        target = options[parent_key]
        if "special" in target:
            result = clean_cache(cache_prefix=target["special"])
        elif "prefix" in target:
            if target.get("show_keys", False) and len(parts) > 1:
                # 用户选择了具体的凭据
                keys = list(cache.find_by_prefix(target["prefix"]))
                try:
                    index = int(parts[1]) - 1
                    if 0 <= index < len(keys):
                        key_to_clean = keys[index]
                        result = clean_cache(cache_key=key_to_clean)
                    else:
                        result = "无效的选项索引"
                except ValueError:
                    result = "无效的选项格式"
            else:
                # 清理整个前缀
                result = clean_cache(cache_prefix=target["prefix"])
        elif "children" in target:
            if len(parts) > 1:
                # 用户输入了子选项，如 "7.1"
                child_key = parts[1].split(".", 1)[0]
                full_child_key = f"{parent_key}.{child_key}"

                if full_child_key in target["children"]:
                    child = target["children"][full_child_key]
                    result = clean_cache(cache_prefix=child["prefix"])
                else:
                    result = f"无效的子选项: {full_child_key}"
            else:
                # 用户只输入了父选项，如 "7"
                # 清理所有子选项
                results = []
                for child_key, child in target["children"].items():
                    prefix = child["prefix"]
                    res = clean_cache(cache_prefix=prefix)
                    results.append(f"{child_key}: {res}")

                if results:
                    result = "\n".join(results)
                else:
                    result = "没有可清理的子选项"
        else:
            result = "无效的选项类型"

    console.print(result + "\n")
    console.rule()
