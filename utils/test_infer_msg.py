from pathlib import Path

import yaml

from embykeeper.telegram.session import ClientsSession
from embykeeper.telegram.pyrogram import Client
from embykeeper.telegram.link import Link
from embykeeper.utils import AsyncTyper, truncate_str
from embykeeper.config import config


app = AsyncTyper()


async def call_infer(tg: Client, url: str = None, analyze: Path = None):
    context = []
    if url:
        if not url.startswith("https://t.me/"):
            print("Invalid Telegram message URL")
            return

        parts = url.split("/")
        if len(parts) < 2:
            print("Invalid URL format")
            return

        chat_id = parts[-2]
        message_id = int(parts[-1])

        async for msg in tg.get_chat_history(chat_id=chat_id, limit=50, offset_id=message_id):
            spec = []
            text = str(msg.caption or msg.text or "")
            spec.append(f"消息发送时间为 {msg.date}")
            if msg.photo:
                spec.append("包含一张照片")
            if msg.reply_to_message_id:
                rmsg = await tg.get_messages(chat_id, msg.reply_to_message_id)
                spec.append(f"回复了消息: {truncate_str(str(rmsg.caption or rmsg.text or ''), 60)}")
            spec = " ".join(spec)
            ctx = truncate_str(text, 180)
            if msg.from_user.name:
                ctx = f"{msg.from_user.name}说: {ctx}"
            if spec:
                ctx += f" ({spec})"
            context.append(ctx)

    messages = []
    if analyze:
        with open(analyze, "r") as f:
            data = yaml.safe_load(f)
            messages = data.get("messages", [])[:100]

    payload = {}
    if context:
        payload["context"] = list(reversed(context))
    if messages:
        payload["messages"] = messages

    print(payload)

    answer, _ = await Link(tg).infer(payload)

    return answer


@app.async_command()
async def main(config_path: Path, url: str = None, analyze: Path = None):
    await config.reload_conf(config_path)
    async with ClientsSession(config.telegram.account) as clients:
        async for _, tg in clients:
            print(await call_infer(tg, url, analyze))
            break


if __name__ == "__main__":
    app()
