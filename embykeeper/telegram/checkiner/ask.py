import asyncio

from pyrogram.handlers import EditedMessageHandler, MessageHandler, DeletedMessagesHandler
from pyrogram.raw.base.messages.bot_callback_answer import BotCallbackAnswer

from embykeeper.runinfo import RunStatus

from ._templ_a import TemplateACheckin

__ignore__ = True


class AskCheckin(TemplateACheckin):
    name = "Ask"
    bot_username = "askUniversal_bot"
    templ_panel_keywords = ["欢迎"]
    bot_checkin_button = ["🧧"]
    bot_success_keywords = ["恭喜获得"]

    async def init(self):
        self.click_counts = 0
        return await super().init()

    async def on_button_answer(self, answer: BotCallbackAnswer):
        self.click_counts += 1
        if self.click_counts > 20:
            return await self.fail()
