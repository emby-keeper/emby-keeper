import asyncio
from datetime import timedelta
from pathlib import Path
from textwrap import indent
from typing import List
import httpx
from platformdirs import user_data_dir
import tomli as tomllib
import yaml

import openai
from pyrogram.types import Message

from embykeeper import __name__ as __product__
from embykeeper.telegram.messager.smart_pornemby import SmartPornembyMessager
from embykeeper.telegram.session import ClientsSession
from embykeeper.utils import AsyncTyper, get_proxy_str, truncate_str
from embykeeper.config import config


app = AsyncTyper()

# 定义历史消息数量常量
HISTORY_MESSAGE_COUNT = 20
SKIP = 5


@app.async_command()
async def main(config_file: Path):
    await config.reload_conf(config_file)
    proxy = get_proxy_str(config.proxy)
    aiclient = openai.AsyncOpenAI(
        api_key=config.openai.api_key,
        base_url=config.openai.base_url,
        http_client=httpx.AsyncClient(proxy=proxy),
    )
    async with ClientsSession(config.telegram.account[:1]) as clients:
        async for tg in clients:
            messager = SmartPornembyMessager(
                {}, config={}, me=tg.me, basedir=Path(user_data_dir(__product__))
            )
            messages_file = await messager.get_spec_path(messager.default_messages)
            with open(messages_file, "r") as f:
                data = yaml.safe_load(f)
                messager.example_messages = data.get("messages", [])[:100]
            messages: List[Message] = []
            async for message in tg.get_chat_history(messager.chat_name):
                messages.append(message)
                if len(messages) > HISTORY_MESSAGE_COUNT:
                    context = []
                    for msg in messages:
                        spec = []
                        text = str(msg.caption or msg.text or "")
                        spec.append(f"消息发送时间为 {msg.date}")
                        if msg.photo:
                            spec.append("包含一张照片")
                        if msg.reply_to_message_id:
                            rmsg = await tg.get_messages(msg.chat.id, msg.reply_to_message_id)
                            spec.append(
                                f"回复了消息: {truncate_str(str(rmsg.caption or rmsg.text or ''), 60)}"
                            )
                        spec = " ".join(spec)
                        ctx = truncate_str(text, 180)
                        if msg.from_user and msg.from_user.name:
                            ctx = f"{msg.from_user.name}说: {ctx}"
                        if spec:
                            ctx += f" ({spec})"
                        context.append(ctx)

                    last_msg = messages[0]
                    use_time = last_msg.date + timedelta(minutes=2)

                    prompt = "我需要你在一个群聊中进行合理的回复."
                    if messager.example_messages:
                        prompt += "\n该群聊的聊天风格类似于以下条目:\n\n"
                        for msg in messager.example_messages:
                            prompt += f"- {msg}\n"
                    if context:
                        prompt += "\n该群聊最近的几条消息及其特征为 (最早到晚):\n\n"
                        for ctx in list(reversed(context)):
                            prompt += f"- {ctx}\n"
                    prompt += "\n其他信息:\n\n"
                    prompt += f"- 我的用户名: {tg.me.name}\n"
                    prompt += f'- 当前时间: {use_time.strftime("%Y-%m-%d %H:%M:%S")}\n'
                    prompt += (
                        "\n请根据以上的信息, 给出一个合理的回复, 要求:\n"
                        "1. 回复必须简短, 不超过20字, 不能含有说明解释, 表情包, 或 emoji\n"
                        "2. 回复必须符合群聊的语气和风格\n"
                        "3. 回复必须自然, 不能太过刻意\n"
                        "4. 回复必须是中文\n\n"
                        "5. 如果其他人正在就某个问题进行讨论不便打断, 或你有不知道怎么回答的问题, 请输出: SKIP\n\n"
                        "6. 如果已经有很长时间没有人说话, 请勿发送继续XX等语句, 此时请输出: SKIP\n\n"
                        "7. 请更加偏重该群聊最近的几条消息, 如果存在近期的讨论, 加入讨论, 偏向于附和, 允许复读他人消息\n\n"
                        "8. 请勿@其他人或呼喊其他人\n\n"
                        "9. 输出内容请勿包含自己的用户名和冒号\n\n"
                        "10. 输出内容请勿重复自己之前说过的话\n\n"
                    )
                    prompt += "\n请直接输出你的回答:"
                    predict = await call_gpt(aiclient, prompt, "gpt-3.5-turbo")
                    context_str = indent("\n".join(context), "    ")
                    print(f"前序消息: \n{context_str}")
                    print(f"预测回答: {predict}")
                    messages = messages[SKIP:]
                    print(f"等待: 10 秒")
                    await asyncio.sleep(10)


async def call_gpt(client: openai.AsyncOpenAI, prompt: str, model: str):
    try:
        completion = await asyncio.wait_for(
            client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
            ),
            20,
        )
        return completion.choices[0].message.content
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    app()
