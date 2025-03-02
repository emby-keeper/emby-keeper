import asyncio
from pathlib import Path
from textwrap import dedent

from loguru import logger
import tomli as tomllib
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message
from pyrogram.enums import ParseMode

from embykeeper.utils import AsyncTyper
from embykeeper.telegram.pyrogram import Client
from embykeeper.config import config
from embykeeper.telegram.session import API_ID, API_HASH

app = AsyncTyper()
app_config = {}


async def dump(client: Client, message: Message):
    if message.text:
        logger.debug(f"<- {message.text}")


async def checkin(client: Client, message: Message):
    url = app_config["url"]
    await client.send_message(
        message.chat.id,
        f"请打开并复制网页的内容, 粘贴回复: [{url}]({url})",
        parse_mode=ParseMode.MARKDOWN,
    )


@app.async_command()
async def main(config_file: Path, url: str):
    await config.reload_conf(config_file)
    app_config["url"] = url
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
        await bot.add_handler(MessageHandler(checkin, filters.command("checkin")))
        logger.info(f"Started listening for commands: @{bot.me.username}.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    app()
