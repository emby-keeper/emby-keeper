from pyrogram.types import Message

from embykeeper.var import console

from ..link import Link
from . import Monitor

__ignore__ = True


class TerminusExamMonitor(Monitor):
    name = "终点站考试辅助"
    chat_name = "EmbyPublicBot"
    chat_keyword = r"(.*?(?:\n(?!本题贡献者).*?)*)\s+本题贡献者"
    allow_edit = True
    additional_auth = ["gpt"]
    debug_no_log = True
    trigger_interval = 0
    trigger_sem = None

    async def init(self):
        self.log.info("您已开启终点站考试辅助, 正在测试答题服务状态.")
        result, _ = await Link(self.client).terminus_answer("请输出'正常'两个字!")
        if result:
            self.log.info("终点站考试辅助正常已启用, 请在机器人触发考试开始.")
            return True
        else:
            self.log.warning("终点站考试辅助服务状态不正常, 请稍后再试.")
            return False

    async def on_trigger(self, message: Message, key, reply):
        self.log.info(f"新题: {key}, 解析中...")
        if message.reply_markup and message.reply_markup.inline_keyboard:
            options = []
            for row in message.reply_markup.inline_keyboard:
                for button in row:
                    options.append(button.text)
        question = f"问题:\n{key}\n选项:\n" + "\n".join(f"- {option}" for option in options)
        result, by = await Link(self.client).terminus_answer(question)
        if result:
            console.rule(title=f"{by} 给出答案")
            console.print(result)
            console.rule()
        else:
            self.log.warning("解析失败! 请自行回答.")
