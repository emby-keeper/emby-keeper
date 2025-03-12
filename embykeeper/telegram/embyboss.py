from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING

from pyrogram.errors import MessageIdInvalid
from pyrogram.types import Message
from pyrogram.raw.types.messages import BotCallbackAnswer

from .pyrogram import Client

if TYPE_CHECKING:
    from loguru import Logger


class EmbybossRegister:
    def __init__(self, client: Client, logger: Logger, username: str, password: str):
        self.client = client
        self.log = logger
        self.username = username
        self.password = password

    async def run(self, bot: str):
        try:
            panel = await self.client.wait_reply(bot, "/start")
        except asyncio.TimeoutError:
            self.log.warning("初始命令无响应, 无法注册.")
            return False

        text = panel.text or panel.caption
        try:
            current_status = re.search(r"当前状态 \| ([^\n]+)", text).group(1).strip()
            register_status = re.search(r"注册状态 \| (True|False)", text).group(1) == "True"
            available_slots = int(re.search(r"可注册席位 \| (\d+)", text).group(1))
        except (AttributeError, ValueError):
            self.log.warning("无法解析界面, 无法注册, 可能您已注册.")
            return False

        if current_status != "未注册":
            self.log.warning("当前状态不是未注册, 无法注册.")
            return False

        if not register_status:
            self.log.debug("未开注, 将继续监控.")
            return False

        if available_slots <= 0:
            self.log.debug("可注册席位不足, 将继续监控.")
            return False

        # 点击创建账户按钮
        buttons = panel.reply_markup.inline_keyboard
        create_button = None
        for row in buttons:
            for button in row:
                if "创建账户" in button.text:
                    create_button = button.text
                    break
            if create_button:
                break

        if not create_button:
            self.log.warning("找不到创建账户按钮, 无法注册.")
            return False

        async with self.client.catch_reply(panel.chat.id) as f:
            try:
                answer: BotCallbackAnswer = await panel.click(create_button)
                if "已关闭" in answer.message:
                    self.log.debug("未开注, 将继续监控.")
                    return False
            except (TimeoutError, MessageIdInvalid):
                pass
            try:
                msg: Message = await asyncio.wait_for(f, 5)
            except asyncio.TimeoutError:
                self.log.warning("创建账户按钮点击无响应, 无法注册.")
                return False

        text = msg.text or msg.caption
        if "您已进入注册状态" not in text:
            self.log.warning("未能正常进入注册状态, 注册失败.")
            return False

        try:
            msg = await self.client.wait_reply(msg.chat.id, f"{self.username} {self.password}")
        except asyncio.TimeoutError:
            self.log.warning("发送凭据后无响应, 无法注册.")
            return False

        msg = await self.client.wait_edit(msg)
        text = msg.text or msg.caption
        if "创建用户成功" not in text:
            self.log.warning("发送凭据后注册失败.")
            return False
        else:
            return True
