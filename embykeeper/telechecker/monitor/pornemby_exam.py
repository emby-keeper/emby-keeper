from pyrogram.types import Message, InlineKeyboardMarkup

from ...utils import truncate_str
from ..link import Link
from .base import Monitor


class PornembyExamMonitor(Monitor):
    name = "Pornemby 科举"
    chat_name = "PornembyFun"
    chat_user = "pornemby_question_bot"
    chat_keyword = r"问题\d：(.*)\n+(A:.*\n+B:.*\n+C:.*\n+D:.*)"

    async def on_trigger(self, message: Message, keys, reply):
        if "答案" in message.text or not isinstance(message.reply_markup, InlineKeyboardMarkup):
            return
        question = truncate_str(keys[0], 20)
        result = await Link(self.client).answer(keys[0] + "\n" + keys[1])
        if result:
            self.log.info(f'检测到新问题: "{question}", 回答: {result}.')
        else:
            self.log.info(f'检测到新问题: "{question}", 但解析回答失败.')
        try:
            await message.click(result)
        except ValueError:
            self.log.info(f"点击失败: {result} 不是可用的答案.")
