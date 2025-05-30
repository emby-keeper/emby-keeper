import asyncio

from ..link import Link
from ..lock import pornfans_alert, pornfans_messager_mids_lock, pornfans_messager_mids
from . import BotCheckin

__ignore__ = True


class PornfansGameGroupCheckin(BotCheckin):
    name = "PornFans 游戏群发言"
    chat_name = "embytestflight"
    additional_auth = ["pornfans_pack"]
    bot_use_captcha = False

    async def send_checkin(self, retry=False):
        if pornfans_alert.get(self.client.me.id, False):
            self.log.warning("签到失败: 由于风险急停不进行发言")
            return await self.fail(message="由于风险急停不进行发言")

        for _ in range(3):
            min_letters = self.config.get("min_letters", self.config.get("letters", 8))
            max_letters = self.config.get("max_letters", 15)
            prompt = self.config.get(
                "prompt",
                f"请输出{min_letters}个字以上, {max_letters}个字以下的中文回复. 你需要进行一个群组聊天中的发言,"
                "表示的意思是 '发言换取答题资格', 你可以口语化一点, 像真人会说的话, 或者有水群一下的意思."
                "必须严格遵守字数要求！禁止输出逗号句号，开头必须有标号'@@@' (不计入字数)",
            )
            answer, by = await Link(self.client).gpt(prompt)
            if not answer:
                continue

            # Extract first valid response that meets the criteria
            valid_messages = [
                l.lstrip("@@@").strip()
                for l in answer.splitlines()
                if l.startswith("@@@") and min_letters <= len(l.lstrip("@@@").strip()) <= max_letters
            ]

            if not valid_messages:
                continue

            message = valid_messages[0]
            self.log.info(f"即将向群组发送水群消息: {message}.")

            await asyncio.sleep(10)
            if retry:
                await asyncio.sleep(self.bot_retry_wait)

            message = await self.send(message)
            if not message:
                await self.fail(message="发送失败")
            else:
                async with pornfans_messager_mids_lock:
                    if self.client.me.id not in pornfans_messager_mids:
                        pornfans_messager_mids[self.me.id] = []
                pornfans_messager_mids[self.me.id].append(message.id)
                await self.finish(message="已发送发言")
            return
        else:
            return await self.fail(message="无法生成发言内容")

    async def message_handler(*args, **kw):
        return
