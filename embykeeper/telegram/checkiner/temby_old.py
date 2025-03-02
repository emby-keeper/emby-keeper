from pyrogram.types import Message

from . import AnswerBotCheckin

__ignore__ = True


class TembyCheckin(AnswerBotCheckin):
    name = "Temby"
    bot_username = "HiEmbyBot"
    bot_checkin_cmd = "/hi"
    bot_success_keywords = ["Checkin successfully"]
    bot_checked_keywords = ["you have checked in already today"]

    async def on_answer(self, message: Message):
        await super().on_answer(message)
        keys = [k.text for r in message.reply_markup.inline_keyboard for k in r]
        if len(keys) == 1:
            await message.click(keys[0])
        else:
            for k in keys:
                if "签到" in k:
                    await message.click(k)
                    return
            else:
                self.log.warning(f"签到失败: 账户错误.")
                return await self.fail()
