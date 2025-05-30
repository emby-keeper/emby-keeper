import asyncio
import base64
import binascii
import os
from pathlib import Path
import re
from typing import Optional, Union

import tomli as tomllib
from loguru import logger
from watchfiles import awatch
from pydantic import ValidationError
from appdirs import user_data_dir

from .utils import ProxyBase, deep_update, show_exception
from .schema import (
    Config,
    EmbyAccount,
    format_errors,
)
from . import __name__ as __product__

logger = logger.bind(scheme="config")


class ConfigManager(ProxyBase):
    __noproxy__ = (
        "windows",
        "public",
        "basedir",
        "_basedir",
        "_conf_file",
        "_cache",
        "_observer",
        "_callbacks",
    )

    def __init__(self, conf_file=None):
        self.windows = False
        self.public = False

        self._basedir = None
        self._conf_file = conf_file
        self._cache = None
        self._observer = None
        self._callbacks = {
            "change": {},  # key -> [callback_funcs]
            "list_change": {},  # key -> [callback_funcs]
        }

    @property
    def basedir(self):
        if not self._basedir:
            return Path(user_data_dir(__product__))
        else:
            return Path(self._basedir)

    @basedir.setter
    def basedir(self, value):
        self._basedir = Path(value)
        if not self._basedir.is_dir():
            self._basedir.mkdir(parents=True, exist_ok=True)

    @property
    def __subject__(self):
        if not self._cache:
            raise RuntimeError("config not loaded")
        return self._cache

    def on_change(self, key, callback):
        """Register a callback for when a config value changes"""
        if key not in self._callbacks["change"]:
            self._callbacks["change"][key] = []
        self._callbacks["change"][key].append(callback)
        return CallbackHandle(self._callbacks["change"][key], callback)

    def on_list_change(self, key, callback):
        """Register a callback for when items in a list change"""
        if key not in self._callbacks["list_change"]:
            self._callbacks["list_change"][key] = []
        self._callbacks["list_change"][key].append(callback)
        return CallbackHandle(self._callbacks["list_change"][key], callback)

    def _process_changes(self, old_config, new_config):
        """Process changes between old and new configs and trigger callbacks"""

        def get_value(config, key):
            try:
                for part in key.split("."):
                    config = getattr(config, part)
                return config
            except AttributeError:
                return None

        # Process changes and deletions
        for key in self._callbacks["change"]:
            old_val = get_value(old_config, key) if old_config else None
            new_val = get_value(new_config, key) if new_config else None

            if old_val != new_val:
                for callback in self._callbacks["change"][key]:
                    try:
                        callback(old_val, new_val)
                    except Exception as e:
                        logger.warning("根据新配置更新程序状态时出错, 您可能需要重新启动程序.")
                        show_exception(e, regular=False)

        # Process list changes
        for key in self._callbacks["list_change"]:
            old_list = get_value(old_config, key) if old_config else []
            new_list = get_value(new_config, key) if new_config else []

            if isinstance(old_list, (list, tuple)) and isinstance(new_list, (list, tuple)):
                # Compare items directly instead of using sets
                added = [item for item in new_list if item not in old_list]
                deleted = [item for item in old_list if item not in new_list]

                if added or deleted:
                    for callback in self._callbacks["list_change"][key]:
                        try:
                            callback(added, deleted)
                        except Exception as e:
                            logger.warning("根据新配置更新程序状态时出错, 您可能需要重新启动程序.")
                            show_exception(e, regular=False)

    def set(self, value: Union[dict, Config]):
        if isinstance(value, dict):
            value = self.validate_config(value)
        if value:
            old_config = self._cache
            self._cache = value
            self._conf_file = None
            self._process_changes(old_config, value)
            return True
        else:
            return False

    @staticmethod
    def generate_example_config():
        """生成配置文件骨架, 并填入生成的信息."""

        from tomlkit import document, nl, comment, item, dumps
        from tomlkit.items import InlineTable
        from faker import Faker
        from faker.providers import internet, profile

        from .telegram.dynamic import get_names
        from . import __version__, __url__

        fake = Faker()
        fake.add_provider(internet)
        fake.add_provider(profile)

        default_config = Config()
        default_emby_account = EmbyAccount(url="http://example.com", username="", password="")

        doc = document()
        doc.add(comment("这是一个配置文件范例."))
        doc.add(comment("所有账户信息为生成, 请填写您的账户信息."))
        doc.add(comment(f"查看帮助与详情: {__url__}#安装与使用"))
        doc.add(nl())

        doc.add(comment("=" * 80))
        doc.add(comment("Emby 保活相关设置"))
        doc.add(comment(f"详见: https://emby-keeper.github.io/guide/配置文件#emby-子项"))
        doc.add(comment("=" * 80))
        c = item({})
        c.add(nl())
        c.add(
            comment(
                '每次进行进行 Emby 保活的当日时间范围, 可以为单个时间 ("8:00AM") 或时间范围 ("<8:00AM,10:00AM>"):'
            )
        )
        c["time_range"] = default_config.emby.time_range
        c.add(nl())
        c.add(comment("每隔几天进行 Emby 保活:"))
        c["interval_days"] = default_config.emby.interval_days
        c.add(nl())
        c.add(comment("最大可同时进行的站点数:"))
        c["concurrency"] = default_config.emby.concurrency
        c.add(nl())
        c.add(comment("=" * 80))
        c.add(comment("Emby 账号, 您可以重复该片段多次以增加多个账号."))
        c.add(comment(f"详见: https://emby-keeper.github.io/guide/配置文件#emby-account-子项"))
        c.add(comment("=" * 80))
        c["account"] = [{}]
        a: InlineTable = c["account"][0]
        a.comment(f"第 1 个账号")
        a.add(nl())
        a.add(comment("站点域名和端口:"))
        a["url"] = fake.url(["https"]).rstrip("/") + ":443"
        a.add(nl())
        a.add(comment("用户名和密码:"))
        a["username"] = fake.profile()["username"]
        a["password"] = fake.password()
        a.add(nl())
        a.add(comment("模拟观看的随机时长范围 (秒), 可以为单个数字 (120) 或时间范围 ([120, 240]):"))
        a["time"] = default_emby_account.time
        a.add(nl())
        a.add(comment("以下为进阶配置, 请取消注释 (删除左侧的 #) 以使用:"))
        a.add(nl())
        a.add(comment("每隔几天进行保活, 默认使用全局设置 emby.interval_days:"))
        a.add(comment(item({"interval_days": default_config.emby.interval_days}).as_string()))
        a.add(comment("每次进行保活的当日时间范围, 默认使用全局设置 emby.time_range:"))
        a.add(comment(item({"time_range": default_config.emby.time_range}).as_string()))
        a.add(comment("无法获取视频长度时, 依然允许播放 (默认最大播放 10 分钟左右, 可能播放超出实际长度):"))
        a.add(comment(item({"allow_stream": True}).as_string()))
        a.add(comment("取消注释以不使用配置文件定义的代理进行连接"))
        a.add(comment(item({"use_proxy": False}).as_string()))
        a.add(comment("取消注释以禁用该账户"))
        a.add(comment(item({"enabled": False}).as_string()))
        doc["emby"] = c

        doc.add(comment(f"第 2 个账号, 如需使用请将该段取消注释并修改, 也可以添加更多账号."))
        a = item(
            {
                "emby": {
                    "account": [
                        {
                            "url": fake.url(["https"]).rstrip("/") + ":443",
                            "username": fake.profile()["username"],
                            "password": fake.password(),
                            "time": default_emby_account.time,
                        }
                    ]
                }
            }
        )
        for line in a.as_string().strip().split("\n"):
            doc.add(comment(line))

        doc.add(nl())
        doc.add(comment("=" * 80))
        doc.add(comment("Telegram 机器人签到相关设置"))
        doc.add(comment(f"详见: https://emby-keeper.github.io/guide/配置文件#checkiner-子项"))
        doc.add(comment("=" * 80))
        c = item({})
        c.add(nl())
        c.add(
            comment(
                '每次进行进行 Telegram 签到的当日时间范围, 可以为单个时间 ("8:00AM") 或时间范围 ("<8:00AM,10:00AM>"):'
            )
        )
        c["time_range"] = default_config.checkiner.time_range
        c.add(nl())
        c.add(comment("各个站点签到将在开始后, 等待一定时间随机启动, 使各站点错开 (分钟):"))
        c["random_start"] = default_config.checkiner.random_start
        c.add(nl())
        c.add(comment("每个站点签到的最大超时时间 (秒):"))
        c["timeout"] = default_config.checkiner.timeout
        c.add(nl())
        c.add(comment("各站点最大可重试次数 (部分站点出于安全考虑有独立的设置):"))
        c["retries"] = 4
        c.add(nl())
        c.add(comment("最大可同时进行的站点数:"))
        c["concurrency"] = 1
        c.add(nl())
        c.add(comment("每隔几天进行签到:"))
        c["interval_days"] = 1
        doc["checkiner"] = c
        c.add(nl())

        c.add(comment("=" * 80))
        c.add(comment("Telegram 账号, 您可以重复该片段多次以增加多个账号."))
        c.add(comment(f"详见: https://emby-keeper.github.io/guide/配置文件#telegram-account-子项"))
        c.add(comment("=" * 80))
        c = item({"account": [{}]})
        a: InlineTable = c["account"][0]
        a.comment(f"第 1 个账号")
        a.add(nl())
        a.add(comment('带国家区号的账户手机号, 一般为 "+86..."'))
        a["phone"] = f'+861{fake.numerify(text="##########")}'
        a.add(nl())
        a.add(comment("启用机器人签到系列功能, 默认启用, 设置为 false 以禁用:"))
        a["checkiner"] = True
        a.add(nl())
        a.add(comment("启用群组监控系列功能, 包括抢邀请码和回答问题等, 默认禁用, 设置为 true 以启用:"))
        a["monitor"] = False
        a.add(nl())
        a.add(comment("启用自动水群系列功能, 风险较高, 默认禁用, 设置为 true 以启用:"))
        a["messager"] = False
        a.add(nl())
        doc["telegram"] = c
        doc.add(comment("针对该账号的独特设置, 如需使用请将该段取消注释并修改. 详见 site 项和 checkiner 项."))
        a_specific = item(
            {
                "telegram": {
                    "account": [
                        {
                            "site": {
                                "checkiner": ["all"],
                            },
                            "checkiner_config": {
                                "interval_days": 1,
                            },
                        }
                    ]
                }
            }
        )
        for line in a_specific.as_string().strip().split("\n")[1:]:
            doc.add(comment(line))

        doc.add(nl())

        doc.add(comment(f"第 2 个账号, 如需使用请将该段取消注释并修改, 也可以添加更多账号."))
        a = item(
            {
                "telegram": {
                    "account": [
                        {
                            "phone": f'+861{fake.numerify(text="##########")}',
                            "checkiner": True,
                            "monitor": False,
                            "messager": False,
                        }
                    ]
                }
            }
        )
        for line in a.as_string().strip().split("\n"):
            doc.add(comment(line))

        doc.add(nl())
        doc.add(comment("=" * 80))
        doc.add(comment("站点相关设置"))
        doc.add(comment("当您需要禁用某些站点时, 请将该段取消注释并修改."))
        doc.add(comment(f"该部分内容是根据 {__product__.capitalize()} {__version__} 生成的."))
        doc.add(comment(f"详见: https://emby-keeper.github.io/guide/配置文件#site-子项"))
        doc.add(comment("=" * 80))
        doc.add(nl())
        doc.add(comment(f'使用 "all" 代表所有签到器, "sgk" 以代表所有社工库签到器.'))
        doc.add(nl())
        doc.add(comment("案例 (启用所有站点, 除了社工库站点):"))
        site = item(
            {
                "site": {
                    "checkiner": ["all", "-sgk"],
                }
            }
        )
        for line in site.as_string().strip().split("\n"):
            doc.add(comment(line))
        doc.add(nl())
        doc.add(comment("案例 (启用默认站点, 额外增加 temby 站点):"))
        site = item(
            {
                "site": {
                    "checkiner": ["+temby"],
                }
            }
        )
        for line in site.as_string().strip().split("\n"):
            doc.add(comment(line))
        doc.add(nl())
        doc.add(comment("可以分别设置各个组件 (机器人签到 / 群组监控 / 自动水群) 的站点:"))
        site = item(
            {
                "site": {
                    "checkiner": ["-terminus", "-temby"],
                    "monitor": ["-misty"],
                    "messager": ["pornfans"],
                }
            }
        )
        for line in site.as_string().strip().split("\n"):
            doc.add(comment(line))
        doc.add(nl())
        site = item(
            {
                "site": {
                    "checkiner": get_names("checkiner"),
                    "monitor": get_names("monitor"),
                    "messager": get_names("messager"),
                }
            }
        )
        doc.add(comment(f"默认启用站点:"))
        for line in site.as_string().strip().split("\n"):
            doc.add(comment(line))
        doc.add(nl())
        site = item(
            {
                "site": {
                    "checkiner": get_names("checkiner", allow_ignore=True),
                    "monitor": get_names("monitor", allow_ignore=True),
                    "messager": get_names("messager", allow_ignore=True),
                }
            }
        )
        doc.add(comment(f"全部可用站点:"))
        for line in site.as_string().strip().split("\n"):
            doc.add(comment(line))
        doc.add(nl())

        doc.add(comment("=" * 80))
        doc.add(comment("代理相关设置"))
        doc.add(
            comment("代理设置, Emby 和 Telegram 均将通过此代理连接, 服务器位于国内时请配置代理并取消注释")
        )
        doc.add(comment(f"详见: https://emby-keeper.github.io/guide/配置文件#proxy-子项"))
        doc.add(comment("=" * 80))
        doc.add(nl())
        proxy = item(
            {
                "proxy": {
                    "hostname": "127.0.0.1",
                    "port": 1080,
                    "scheme": "socks5",
                }
            }
        )
        proxy["proxy"]["scheme"].comment("可选: http / socks5")
        for line in proxy.as_string().strip().split("\n"):
            doc.add(comment(line))
        doc.add(nl())

        doc.add(comment("=" * 80))
        doc.add(comment("日志推送相关设置"))
        doc.add(comment(f"详见: https://emby-keeper.github.io/guide/配置文件#notifier-子项"))
        doc.add(comment("=" * 80))
        c = item({})
        c.add(nl())
        c.add(comment("启用签到/保活结果的日志推送:"))
        c["enabled"] = True
        c.add(comment("使用第几个 Telegram 账号进行推送, 从 1 开始计数:"))
        c["account"] = 1
        c.add(
            comment(
                "默认情况下, 日志推送将在每天指定时间统一推送 (在 @embykeeper_bot 设置), 设置为 false 以立刻推送"
            )
        )
        c["immediately"] = False
        c.add(comment("默认情况下, 启动时立刻执行的一次签到/保活不会推送消息, 设置为 true 以推送"))
        c["once"] = False
        doc["notifier"] = c
        doc.add(nl())

        doc.add(comment("=" * 80))
        doc.add(comment("Subsonic 保活相关设置 (包括 Navidrome 和其他支持 Subsonic API 的音乐服站点)"))
        doc.add(comment(f"详见: https://emby-keeper.github.io/guide/配置文件#subsonic-子项"))
        doc.add(comment("=" * 80))
        c = item({})
        c.add(nl())
        c.add(
            comment(
                '每次进行进行 Subsonic 保活的当日时间范围, 可以为单个时间 ("8:00AM") 或时间范围 ("<8:00AM,10:00AM>"):'
            )
        )
        c["time_range"] = default_config.subsonic.time_range
        c.add(nl())
        c.add(comment("每隔几天进行 Subsonic 保活:"))
        c["interval_days"] = default_config.subsonic.interval_days
        c.add(nl())
        c.add(comment("最大可同时进行的站点数:"))
        c["concurrency"] = default_config.subsonic.concurrency
        doc["subsonic"] = c

        doc.add(nl())
        doc.add(comment("=" * 80))
        doc.add(comment("Subsonic 账号, 您可以重复该片段多次以增加多个账号, 如需使用, 请取消注释."))
        doc.add(comment(f"详见: https://emby-keeper.github.io/guide/配置文件#subsonic-account-子项"))
        doc.add(comment("=" * 80))
        doc.add(nl())

        cd = item({})
        cd["subsonic"] = {"account": [{}, {}]}
        c = cd["subsonic"]
        for i in range(2):
            a: InlineTable = c["account"][i]
            a.comment(f"第 {i + 1} 个账号")
            if not i:
                a.add(nl())
                a.add(comment("站点域名和端口:"))
            a["url"] = fake.url(["https"]).rstrip("/") + ":443"
            if not i:
                a.add(nl())
                a.add(comment("用户名和密码:"))
            a["username"] = fake.profile()["username"]
            a["password"] = fake.password()
            if not i:
                a.add(nl())
                a.add(comment("模拟观看的随机时长范围 (秒), 可以为单个数字 (120) 或时间范围 ([120, 240]):"))
            a["time"] = default_emby_account.time
            if not i:
                a.add(nl())

        for line in cd.as_string().strip().split("\n"):
            doc.add(comment(line))

        return dumps(doc)

    def reset(self):
        self._cache = None

    @staticmethod
    def validate_config(config: Optional[dict] = None):
        """验证配置文件格式"""
        if config is None:
            return None
        try:
            return Config(**config)
        except ValidationError as e:
            logger.error(format_errors(e))
            return None

    async def start_observer(self):
        async def observer():
            async for changes in awatch(self._conf_file):
                logger.info(f"配置文件已更改，正在重新加载.")
                await self.reload_conf(self._conf_file)

        if self._observer:
            self._observer.cancel()
            asyncio.gather(self._observer, return_exceptions=True)
        self._observer = asyncio.create_task(observer())

    @staticmethod
    def load_config_str(data: str):
        """从环境变量数据读入配置."""

        try:
            data = base64.b64decode(re.sub(r"\s+", "", data).encode())
        except binascii.Error:
            logger.error("环境变量 EK_CONFIG 定义的配置格式错误, 请调整并重试.")
            return None
        try:
            config = tomllib.loads(data.decode())
        except (tomllib.TOMLDecodeError, UnicodeDecodeError):
            logger.error("环境变量 EK_CONFIG 定义的配置格式错误, 请调整并重试.")
            return None
        else:
            logger.debug("您正在使用环境变量配置.")
        return config

    async def reload_conf(self, conf_file=None):
        """Load config from provided file or config.toml at cwd."""
        cfg_dict = {}
        env_config = os.environ.get(f"EK_CONFIG", None)
        if env_config:
            cfg_dict.update(self.load_config_str(env_config))
        else:
            if self.windows:
                default_conf_file = self.basedir / "config.toml"
            else:
                default_conf_file = Path("config.toml")
            if conf_file:
                conf_file = Path(conf_file)
            elif self._conf_file:
                conf_file = Path(self._conf_file)
            elif default_conf_file.is_file():
                conf_file = default_conf_file
            if conf_file:
                if conf_file.suffix.lower() == ".toml":
                    try:
                        with open(conf_file, "rb") as f:
                            deep_update(cfg_dict, tomllib.load(f))
                    except tomllib.TOMLDecodeError as e:
                        logger.error(f'配置文件 "{conf_file}" 中的 TOML 格式错误:\n\t{e}.')
                else:
                    logger.error(f'配置文件 "{conf_file}" 不是 TOML 格式的配置文件.')
                    return False
            else:
                try:
                    with open(default_conf_file, "w+", encoding="utf-8") as f:
                        f.write(self.generate_example_config())
                except OSError as e:
                    logger.error(
                        f'无法写入默认配置文件 "{default_conf_file}", 请确认是否有权限进行该目录写入: {e}.'
                    )
                    return False
                logger.warning("需要一个 TOML 格式的配置文件.")
                logger.warning(f'您可以根据生成的参考配置文件 "{default_conf_file}" 进行配置')
                return False

        cfg_model = self.validate_config(cfg_dict)
        if not cfg_model:
            return False

        if conf_file:
            logger.debug(f"现在使用的配置文件为: {conf_file.absolute()}")
            self.set(cfg_model)
            if not self._conf_file == conf_file:
                self._conf_file = conf_file
                await self.start_observer()
            return True


class CallbackHandle:
    def __init__(self, callback_list, callback):
        self._callback_list = callback_list
        self._callback = callback

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._callback in self._callback_list:
            self._callback_list.remove(self._callback)


config: Union[Config, ConfigManager] = ConfigManager()

if __name__ == "__main__":
    print(config.generate_example_config())
