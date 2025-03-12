import random
import re
import string
from typing import List, Union
from loguru import logger
from pydantic import BaseModel, ValidationError
from pyrogram.types import Message

from . import Monitor
from ..embyboss import EmbybossRegister

__ignore__ = True


class TemplateAMonitorConfig(BaseModel):
    name: str = None
    chat_name: Union[str, int] = None  # 监控的群聊名称
    chat_allow_outgoing: bool = False  # 是否支持自己发言触发
    chat_user: Union[str, List[str]] = []  # 仅被列表中用户的发言触发 (支持 username / userid)
    chat_keyword: Union[str, List[str]] = []  # 仅当消息含有列表中的关键词时触发, 支持 regex
    chat_except_keyword: Union[str, List[str]] = []  # 消息含有列表中的关键词时不触发, 支持 regex
    chat_probability: float = 1.0  # 发信概率 (0最低, 1最高)
    chat_delay: int = 0  # 发信延迟 (s)
    chat_follow_user: int = 0  # 需要等待 N 个用户发送 {chat_reply} 方可回复
    chat_reply: str = None  # 回复的内容, 可以为恒定字符串或函数或异步函数
    allow_edit: bool = False  # 编辑消息内容后也触发
    trigger_interval: float = 2  # 每次触发的最低时间间隔
    trigger_sim: int = 1  # 同时触发的最大并行数
    trigger_max_time: float = 120  # 触发后处理的最长时间
    allow_caption: bool = True  # 是否允许带照片的消息
    allow_text: bool = True  # 是否允许不带照片的消息
    send: bool = True  # 是否发送通知
    send_immediately: bool = True  # 是否发送即时日志, 不等待每日推送时间
    try_register_bot: str = None  # 尝试注册的机器人名称 (需为: https://github.com/berry8838/Sakura_embyboss)


class TemplateAMonitor(Monitor):
    init_first = True
    additional_auth = ["prime"]
    notify_create_name = True

    async def init(self):
        try:
            self.t_config = TemplateAMonitorConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"初始化失败: 监控器自定义模板 A 的配置错误:\n{e}")
            return False
        self.name = self.t_config.name or "自定义"
        self.chat_name = self.t_config.chat_name
        self.chat_allow_outgoing = self.t_config.chat_allow_outgoing
        self.chat_user = self.t_config.chat_user
        self.chat_keyword = self.t_config.chat_keyword
        self.chat_except_keyword = self.t_config.chat_except_keyword
        self.chat_probability = self.t_config.chat_probability
        self.chat_delay = self.t_config.chat_delay
        self.chat_follow_user = self.t_config.chat_follow_user
        self.chat_reply = self.t_config.chat_reply
        self.allow_edit = self.t_config.allow_edit
        self.trigger_interval = self.t_config.trigger_interval
        self.trigger_sim = self.t_config.trigger_sim
        self.trigger_max_time = self.t_config.trigger_max_time
        self.allow_caption = self.t_config.allow_caption
        self.allow_text = self.t_config.allow_text
        if (not self.chat_keyword) and (not self.chat_user) and (not self.chat_name):
            self.log.warning(f"初始化失败: 没有定义任何监控项, 请参考教程进行配置.")
            return False
        self.log = logger.bind(scheme="telemonitor", name=self.name, username=self.client.me.name)
        return True

    async def on_trigger(self, message: Message, key, reply):
        content = message.text or message.caption
        if self.t_config.send:
            if message.from_user:
                msg = f"监控器 {self.name} 收到来自 {message.from_user.name} 的关键消息: {content}"
            else:
                msg = f"监控器 {self.name} 收到关键消息: {content}"
            if self.t_config.send_immediately:
                self.log.bind(msg=True).info(msg)
            else:
                self.log.bind(log=True).info(msg)
        if self.t_config.try_register_bot:
            random_code = "".join(random.choices(string.ascii_letters + string.digits, k=4))
            if await EmbybossRegister(self.client, self.log, self.unique_name, random_code).run(
                self.t_config.try_register_bot
            ):
                self.log.bind(log=True).info(
                    f"监控器 {self.name} 成功注册机器人 {self.t_config.try_register_bot}."
                )

    def get_unique_name(self):
        if not self.t_config.try_register_bot:
            return None
        unique_name = self.config.get("unique_name", None)
        if unique_name:
            self.log.info(f'根据您的设置, 当监控到开注时, 该站点将以用户名 "{unique_name}" 注册.')
            if not re.search("^\w+$", unique_name):
                self.log.warning(f"用户名含有除 a-z, A-Z, 0-9, 以及下划线之外的字符, 可能导致注册失败.")
            return unique_name
        else:
            return Monitor.unique_cache[self.client.me]


def use(**kw):
    return type("TemplatedClass", (TemplateAMonitor,), kw)
