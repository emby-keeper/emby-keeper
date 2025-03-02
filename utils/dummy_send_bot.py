import asyncio
from functools import partial
import json
from pathlib import Path
from typing import Dict, List

from loguru import logger
import tomli as tomllib
from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import (
    Message,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    MessageEntity,
    CallbackQuery,
)
from pyrogram.enums import ParseMode, MessageEntityType

from embykeeper.utils import AsyncTyper
from embykeeper.telegram.pyrogram import Client
from embykeeper.config import config
from embykeeper.telegram.session import API_ID, API_HASH

user_states = {}

app = AsyncTyper()


async def callback(client: Client, callback_query: CallbackQuery):
    print(f"收到 Callback 信息: {callback_query.data}")
    await callback_query.answer()


async def dump(client: Client, message: Message):
    if message.text:
        logger.debug(f"<- {message.text}")


async def start(client: Client, message: Message):
    await client.send_message(message.chat.id, "你好! 请使用命令!")


async def parse(client: Client, message: Message, updates: List[Dict]):
    for u in updates:
        if not u.get("_", None) == "Message":
            continue
        reply_markup = u.get("reply_markup", None)
        if reply_markup:
            if reply_markup["_"] == "InlineKeyboardMarkup":
                keyboard = reply_markup["inline_keyboard"]
                _reply_markup = []
                for row in keyboard:
                    _row = []
                    for key in row:
                        _row.append(
                            InlineKeyboardButton(
                                key["text"],
                                callback_data=key.get("callback_data", None),
                                url=key.get("url", None),
                            )
                        )
                    _reply_markup.append(_row)
                _reply_markup = InlineKeyboardMarkup(_reply_markup)
        else:
            _reply_markup = None
        entities = u.get("entities", u.get("caption_entities", None))
        if entities:
            _entities = []
            for e in entities:
                type_str = e["type"].split(".")[1]
                type = getattr(MessageEntityType, type_str)
                kw = {"offset": e["offset"], "length": e["length"]}
                if type == MessageEntityType.TEXT_LINK:
                    kw["url"] = e["url"]
                elif type == MessageEntityType.TEXT_MENTION:
                    kw["user"] = message.from_user
                elif type == MessageEntityType.CUSTOM_EMOJI:
                    kw["custom_emoji_id"] = e["custom_emoji_id"]
                _entities.append(MessageEntity(type=type, **kw))
        else:
            _entities = None
        text = u.get("text", u.get("caption", ""))
        if u.get("media", None) == "MessageMediaType.PHOTO":
            await client.send_photo(
                message.chat.id,
                Path(__file__).parent.parent / "images" / "kitty.gif",
                caption_entities=_entities,
                caption=text,
                parse_mode=ParseMode.DISABLED,
                reply_markup=_reply_markup,
            )
        else:
            await client.send_message(
                message.chat.id,
                text,
                entities=_entities,
                parse_mode=ParseMode.DISABLED,
                reply_markup=_reply_markup,
            )


@app.async_command()
async def main(config_file: Path, updates_file: Path):
    await config.reload_conf(config_file)
    with open(updates_file, "r") as f:
        try:
            updates = json.load(f)
        except json.JSONDecodeError:
            updates = []
            f.seek(0)
            for chunk in f.read().split("\n}\n"):
                chunk = chunk.strip()
                if chunk:
                    updates.append(json.loads(chunk + "\n}"))
    logger.info(f"更新文件内有 {len(updates)} 条消息.")
    bot = Client(
        name="test_bot",
        bot_token=config.bot.token,
        proxy=config.proxy.model_dump(),
        workdir=Path(__file__).parent,
        api_id=API_ID,
        api_hash=API_HASH,
        in_memory=True,
    )
    async with bot:
        await bot.add_handler(MessageHandler(dump), group=1)
        await bot.add_handler(MessageHandler(start, filters.command("start")))
        await bot.add_handler(MessageHandler(partial(parse, updates=updates), filters.command("parse")))
        await bot.add_handler(CallbackQueryHandler(callback))
        await bot.set_bot_commands(
            [
                BotCommand("start", "Start the bot"),
                BotCommand("parse", "Parse messages"),
            ]
        )
        logger.info(f"Started listening for commands: @{bot.me.username}.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    app()
