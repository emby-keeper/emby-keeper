import asyncio
import random
import string
from typing import Optional

from pydantic import BaseModel, ValidationError

from embykeeper.telegram.embyboss import EmbybossRegister
from embykeeper.runinfo import RunStatus

from . import BaseBotRegister

__ignore__ = True


class TemplateARegisterConfig(BaseModel):
    name: Optional[str] = None
    username: Optional[str] = None  # 可选, 不填则自动生成
    password: Optional[str] = None  # 可选, 不填则自动生成


class TemplateARegister(BaseBotRegister):
    def __init__(self, client, context=None, retries=None, timeout=None, config=None, **kwargs):
        # 设置基本属性
        self.bot_username = kwargs.get("bot_username") or getattr(self.__class__, "bot_username", None)
        self.name = kwargs.get("name", f"@{self.bot_username}")
        self.templ_name = kwargs.get("templ_name") or getattr(self.__class__, "templ_name", None)

        # 调用父类构造函数
        super().__init__(client, context, retries, timeout, config)

        try:
            self.t_config = TemplateARegisterConfig.model_validate(self.config)
        except ValidationError as e:
            self.log.warning(f"初始化失败: 注册自定义模板 A 的配置错误:\n{e}")
            self.t_config = TemplateARegisterConfig()  # 使用默认配置

    async def start(self):
        if not self.bot_username:
            self.log.warning("未配置bot_username, 无法进行注册")
            return self.ctx.finish(RunStatus.FAIL, "未配置bot_username")

        for attempt in range(self.retries + 1):
            try:
                username = self.t_config.username or self.client.me.username or f"user_{self.client.me.id}"
                password = self.t_config.password or "".join(
                    random.choices(string.ascii_letters + string.digits, k=4)
                )

                embyboss_register = EmbybossRegister(
                    client=self.client, logger=self.log, username=username, password=password
                )

                # 使用超时控制
                success = await asyncio.wait_for(
                    embyboss_register.run(self.bot_username), timeout=self.timeout
                )

                if success:
                    self.log.info("注册成功")
                    return self.ctx.finish(RunStatus.SUCCESS, "注册成功")
                else:
                    if attempt < self.retries:
                        self.log.warning(f"注册失败, 将进行第 {attempt + 2} 次重试")
                        await asyncio.sleep(1)  # 重试间隔
                        continue
                    else:
                        self.log.warning("注册失败, 已达到最大重试次数")
                        return self.ctx.finish(RunStatus.FAIL, "注册失败")

            except asyncio.TimeoutError:
                if attempt < self.retries:
                    self.log.warning(f"注册超时 ({self.timeout}秒), 将进行第 {attempt + 2} 次重试")
                    await asyncio.sleep(1)  # 重试间隔
                    continue
                else:
                    self.log.error(f"注册超时, 已达到最大重试次数")
                    return self.ctx.finish(RunStatus.FAIL, f"注册超时 ({self.timeout}秒)")
            except Exception as e:
                if attempt < self.retries:
                    self.log.warning(f"注册异常: {e}, 将进行第 {attempt + 2} 次重试")
                    await asyncio.sleep(1)  # 重试间隔
                    continue
                else:
                    self.log.error(f"注册过程中发生异常: {e}, 已达到最大重试次数")
                    return self.ctx.finish(RunStatus.FAIL, f"注册异常: {e}")

        return self.ctx.finish(RunStatus.FAIL, "注册失败")


def use(**kw):
    return type("TemplatedRegisterClass", (TemplateARegister,), kw)
