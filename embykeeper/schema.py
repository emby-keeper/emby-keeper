from typing import List, Optional, Union, Dict, Any, ClassVar
from pydantic import BaseModel, Field, model_validator, ValidationError
from pydantic.networks import HttpUrl

DEFAULT_TIME_RANGE = "<11:00AM,11:00PM>"
DEFAULT_EMBY_INTERVAL_DAYS = "<7,12>"


class ConfigModel(BaseModel):
    model_config = {"extra": "forbid"}

    @model_validator(mode="before")
    @classmethod
    def validate_extra_fields(cls, values):
        if not isinstance(values, dict):
            return values
        if cls.model_config.get("extra") == "allow":
            return values
        allowed_fields = set(cls.model_fields.keys())
        extra_fields = set(values.keys()) - allowed_fields
        if extra_fields:
            raise ValueError(
                f"包含未知设置项：{', '.join(extra_fields)}, 允许的设置项: {', '.join(allowed_fields)}"
            )
        return values


class UseStr(str):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info):
        if isinstance(v, (int, float)):
            return str(v)
        return v


class UseHttpUrl(HttpUrl):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v, info):
        if isinstance(v, str) and not v.startswith(("http://", "https://")):
            v = f"https://{v}"
        return HttpUrl(v)


class ProxyConfig(ConfigModel):
    hostname: Optional[str] = None
    port: Optional[int] = Field(None, gt=0)
    scheme: Optional[str] = Field(None, pattern="^(socks5|http)$")
    username: Optional[str] = None
    password: Optional[str] = None


class CheckinerConfig(ConfigModel):
    time_range: Optional[UseStr] = DEFAULT_TIME_RANGE
    interval_days: Optional[UseStr] = "1"
    timeout: Optional[int] = 120
    retries: Optional[int] = 4
    concurrency: Optional[int] = 1
    random_start: Optional[int] = 60

    model_config = {"extra": "allow"}

    def get_site_config(self, site: str) -> Dict[str, Any]:
        return getattr(self, site, {})


class MonitorConfig(ConfigModel):
    model_config = {"extra": "allow"}

    def get_site_config(self, site: str) -> Dict[str, Any]:
        return getattr(self, site, {})


class MessagerConfig(ConfigModel):
    model_config = {"extra": "allow"}

    def get_site_config(self, site: str) -> Dict[str, Any]:
        return getattr(self, site, {})


class NotifierConfig(ConfigModel):
    enabled: Optional[bool] = False
    account: Optional[Union[int, str]] = 1
    immediately: Optional[bool] = False
    once: Optional[bool] = False


class SiteConfig(ConfigModel):
    checkiner: Optional[List[str]] = None
    monitor: Optional[List[str]] = None
    messager: Optional[List[str]] = None


class MediaServerBaseConfig(ConfigModel):
    time_range: Optional[UseStr] = DEFAULT_TIME_RANGE
    interval_days: Optional[UseStr] = DEFAULT_EMBY_INTERVAL_DAYS
    concurrency: Optional[int] = 1
    retries: Optional[int] = 5


class EmbyAccount(ConfigModel):
    url: UseHttpUrl
    username: str
    password: str
    name: str = None
    time: Optional[Union[int, List[int]]] = [300, 600]
    continuous: Optional[bool] = False
    useragent: Optional[str] = None
    client: Optional[str] = None
    client_version: Optional[str] = None
    device: Optional[str] = None
    device_id: Optional[str] = None
    allow_multiple: Optional[bool] = True
    allow_stream: Optional[bool] = False
    cf_challenge: Optional[bool] = True
    use_proxy: Optional[bool] = True
    play_id: Optional[str] = None
    enabled: Optional[bool] = True

    # 站点单独配置
    interval_days: Optional[Union[int, str]] = None
    time_range: Optional[str] = None

    # 向后兼容字段
    interval: Optional[Union[int, str]] = None
    watchtime: Optional[str] = None
    hide: Optional[bool] = None
    ua: Optional[str] = None
    jellyfin: Optional[bool] = None


class EmbyConfig(MediaServerBaseConfig):
    account: Optional[List[EmbyAccount]] = []


class SubsonicAccount(ConfigModel):
    url: UseHttpUrl
    username: str
    password: str
    name: str = None
    time: Optional[Union[int, List[int]]] = None
    useragent: Optional[str] = None
    client: Optional[str] = None
    client_version: Optional[str] = None
    use_proxy: Optional[bool] = True
    enabled: Optional[bool] = True

    # 站点单独配置
    interval_days: Optional[Union[int, str]] = None
    time_range: Optional[str] = None

    # 向后兼容字段
    ua: Optional[str] = None
    version: Optional[str] = None


class SubsonicConfig(MediaServerBaseConfig):
    account: Optional[List[SubsonicAccount]] = []


class TelegramAccount(ConfigModel):
    phone: str = Field(description="Telegram phone number")

    @model_validator(mode="before")
    @classmethod
    def clean_phone(cls, values):
        if isinstance(values, dict) and "phone" in values:
            values["phone"] = values["phone"].replace(" ", "")
        return values

    checkiner: Optional[bool] = True
    monitor: Optional[bool] = False
    messager: Optional[bool] = False
    api_id: Optional[str] = None
    api_hash: Optional[str] = None
    session: Optional[str] = None
    enabled: Optional[bool] = True

    # 账号单独配置
    site: Optional[SiteConfig] = None
    checkiner_config: Optional[CheckinerConfig] = None

    def get_config_key(self):
        import hashlib

        unique_str = f"{self.phone}:{self.api_id or ''}:{self.api_hash or ''}"
        hash_value = hashlib.sha256(unique_str.encode()).hexdigest()[:8]
        return f"{self.phone}/{hash_value}"


class TelegramConfig(ConfigModel):
    account: Optional[List[TelegramAccount]] = []


class BotConfig(ConfigModel):
    token: str


class Config(ConfigModel):
    alias_map: ClassVar[Dict[str, str]] = {
        "emby.time_range": "watchtime",
        "emby.concurrency": "watch_concurrent",
        "subsonic.time_range": "listentime",
        "subsonic.concurrency": "listen_concurrent",
        "checkiner.time_range": "time",
        "checkiner.timeout": "timeout",
        "checkiner.retries": "retries",
        "checkiner.concurrency": "concurrent",
        "checkiner.random_start": "random",
        "emby.interval_days": "interval",
        "subsonic.interval_days": "interval",
        "site": "service",
    }

    mongodb: Optional[str] = None
    basedir: Optional[str] = None
    nofail: Optional[bool] = True
    debug_cron: Optional[bool] = False
    proxy: Optional[ProxyConfig] = None
    emby: Optional[EmbyConfig] = EmbyConfig()
    subsonic: Optional[SubsonicConfig] = SubsonicConfig()
    checkiner: Optional[CheckinerConfig] = CheckinerConfig()
    monitor: Optional[MonitorConfig] = MonitorConfig()
    messager: Optional[MessagerConfig] = MessagerConfig()
    telegram: Optional[TelegramConfig] = TelegramConfig()
    notifier: Optional[NotifierConfig] = NotifierConfig()
    site: Optional[SiteConfig] = None

    # 向后兼容字段
    time: Optional[str] = None
    watchtime: Optional[str] = None
    listentime: Optional[str] = None
    interval: Optional[Union[int, str]] = None
    timeout: Optional[int] = None
    retries: Optional[int] = None
    concurrent: Optional[int] = None
    watch_concurrent: Optional[int] = None
    listen_concurrent: Optional[int] = None
    random: Optional[int] = None
    notify_immediately: Optional[bool] = None
    service: Optional[SiteConfig] = None

    # 调试字段
    bot: Optional[BotConfig] = None

    @model_validator(mode="before")
    @classmethod
    def handle_aliases(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        for service in ["emby", "subsonic", "telegram"]:
            if service in values and isinstance(values[service], list):
                if service == "telegram":
                    # Convert telegram account fields
                    for account in values[service]:
                        if "send" in account:
                            account["messager"] = account.pop("send")
                        if "checkin" in account:
                            account["checkiner"] = account.pop("checkin")
                if service == "emby":
                    # Convert emby account fields
                    for account in values[service]:
                        if "ua" in account:
                            account["useragent"] = account.pop("ua")
                if service == "subsonic":
                    # Convert subsonic account fields
                    for account in values[service]:
                        if "ua" in account:
                            account["useragent"] = account.pop("ua")
                        if "version" in account:
                            account["client_version"] = account.pop("version")
                values[service] = {"account": values[service]}

        if "notifier" in values:
            notifier_value = values["notifier"]
            if isinstance(notifier_value, str):
                values["notifier"] = {
                    "enabled": True,
                    "account": notifier_value,
                }
            elif isinstance(notifier_value, bool):
                values["notifier"] = {
                    "enabled": notifier_value,
                }
            elif isinstance(notifier_value, int):
                values["notifier"] = {
                    "enabled": notifier_value > 0,
                    "account": notifier_value,
                }

        for new_field, old_field in cls.alias_map.items():
            if old_field in values and values[old_field] is not None:
                parts = new_field.split(".")
                target = values
                for part in parts[:-1]:
                    target.setdefault(part, {})
                    target = target[part]
                target[parts[-1]] = values[old_field]

        return values


def format_errors(e: ValidationError) -> str:
    """自定义错误信息格式化"""

    error_translations = {
        "Input should be a valid boolean": "输入应为布尔值 (true/false)",
        "Input should be a valid integer": "输入应为有效的整数",
        "Input should be a valid string": "输入应为有效的字符串, 用英文双引号包裹",
        "Input should be a valid list": "输入应为有效的列表, 用[]符号包裹",
        "Input should be a valid URL": "输入应为有效的URL地址",
        "Field required": "必填字段",
        "Value error": "配置验证错误",
        "Input should match pattern": "输入格式不匹配要求",
        "Value is not a valid dict": "输入应为有效的字典格式",
    }

    reverse_aliases = {}
    for new_field, old_field in Config.alias_map.items():
        if old_field not in reverse_aliases:
            reverse_aliases[old_field] = []
        reverse_aliases[old_field].append(new_field)

    error_groups = {}
    error_messages = ["配置文件错误，请检查配置文件:"]

    for error in e.errors():
        location = list(error["loc"])
        msg = error["msg"]

        # 翻译错误消息
        for eng, chn in error_translations.items():
            if callable(chn):
                msg = msg.replace(eng, chn(error["loc"]))
            else:
                msg = msg.replace(eng, chn)

        # 如果是根级别的错误，直接添加错误信息
        if not location:
            error_messages.append(f"  {msg}")
            continue

        loc_str = " -> ".join(str(loc) for loc in location)

        error_key = (() if len(location) <= 1 else tuple(location[1:])) + (msg,)

        # 检查是否有相关的别名字段
        if location[0] in reverse_aliases:
            for new_field in reverse_aliases[location[0]]:
                new_loc = new_field.split(".")
                if len(location) > 1:
                    new_loc.extend(location[1:])
                new_loc_str = " -> ".join(new_loc)
                group_key = f"  {new_loc_str}\n  (旧版本为: {loc_str})"
                error_groups[error_key] = (group_key, msg)
        else:
            error_groups[error_key] = (f"  {loc_str}", msg)

    # 添加分组后的错误消息
    for _, (location, msg) in error_groups.items():
        error_messages.append(f"{location}:")
        error_messages.append(f"    {msg}")

    error_messages.append("详细说明请访问: https://emby-keeper.github.io/guide/配置文件")
    return "\n".join(error_messages)


if __name__ == "__main__":
    import sys
    import tomli
    import pprint

    if len(sys.argv) < 2:
        print("Usage: python schema.py <config.toml>")
        sys.exit(1)

    try:
        with open(sys.argv[1], "rb") as f:
            config_dict = tomli.load(f)
        config = Config(**config_dict)
        pprint.pprint(config.model_dump())
    except FileNotFoundError:
        print(f"错误: 配置文件 '{sys.argv[1]}' 未找到")
        sys.exit(1)
    except tomli.TOMLDecodeError as e:
        print(f"错误: TOML格式无效 - {e}")
        sys.exit(1)
    except ValidationError as e:
        print(format_errors(e))
        sys.exit(1)
