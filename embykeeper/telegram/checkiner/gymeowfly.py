from pyrogram.errors import MessageIdInvalid, DataInvalid
from pyrogram.types import Message

from . import TemplateACheckin


class GymeowflyCheckin(TemplateACheckin):
    name = "喵了个咪"
    bot_username = "gymeowfly_bot"
    bot_checkin_cmd = ["/start"]
    bot_use_captcha = False
    templ_panel_keywords = ["签到", "我不是机器人"]
    bot_use_history = 10

    async def message_handler(self, client, message: Message):
        keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
        for k in keys:
            if any(key in k for key in self.templ_panel_keywords):
                try:
                    res = await message.click(k)
                    if "先点击一次签到按钮" in res.message:
                        return await self.retry()
                    if "已经签到过了" in res.message:
                        return await self.finish()
                except (TimeoutError, MessageIdInvalid, DataInvalid):
                    pass
                return

        if message.text and "请先加入聊天群组和通知频道" in message.text:
            self.log.warning(f"签到失败: 账户错误.")
            return await self.fail()

        await super().message_handler(client, message)
