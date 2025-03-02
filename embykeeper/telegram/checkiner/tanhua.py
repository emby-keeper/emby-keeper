from pyrogram.types import Message
from pyrogram.errors import MessageIdInvalid, DataInvalid

from embykeeper.utils import to_iterable

from . import AnswerBotCheckin, MessageType


class TanhuaCheckin(AnswerBotCheckin):
    name = "探花"
    bot_username = "TanhuaTvBot"
    additional_auth = ["prime"]
    bot_checkin_cmd = ["/start"]
    templ_panel_keywords = ["请选择功能", "用户面板", "用户名称"]
    bot_success_keywords = ["签到获得积分"]
    bot_checked_keywords = ["今日已签到"]
    bot_text_ignore = ["请选择正确的验证码"]
    bot_use_history = 10
    bot_answer_button_message_pat = "请选择正确的验证码"

    async def message_handler(self, client, message: Message):
        text = message.caption or message.text
        if (
            text
            and any(keyword in text for keyword in to_iterable(self.templ_panel_keywords))
            and message.reply_markup
        ):
            keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
            for k in keys:
                if "个人信息" in k:
                    try:
                        await message.click(k)
                    except (TimeoutError, MessageIdInvalid, DataInvalid):
                        pass
                    return
                if "签到" in k or "簽到" in k:
                    try:
                        await message.click(k)
                    except TimeoutError:
                        self.log.debug(f"点击签到按钮无响应, 可能按钮未正确处理点击回复. 一般来说不影响签到.")
                    except (MessageIdInvalid, DataInvalid):
                        pass
                    return
            else:
                self.log.warning(f"签到失败: 账户错误.")
                return await self.fail()

        if message.text and "请先加入聊天群组和通知频道" in message.text:
            self.log.warning(f"签到失败: 账户错误.")
            return await self.fail()

        await super().message_handler(client, message)

    def _message_type(self, message: Message):
        if message.photo:
            if message.caption:
                return MessageType.CAPTION
            else:
                return MessageType.CAPTCHA
        elif message.text:
            return MessageType.TEXT
        elif message.document:
            return MessageType.CAPTCHA
        else:
            return MessageType.IGNORE

    def message_type(self, message: Message):
        if self.is_valid_answer(message):
            return MessageType.ANSWER | self._message_type(message)
        else:
            return self._message_type(message)
