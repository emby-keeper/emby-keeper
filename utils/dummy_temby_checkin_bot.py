import asyncio
from pathlib import Path

from loguru import logger
import tomli as tomllib
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton

from embykeeper.utils import AsyncTyper
from embykeeper.telegram.pyrogram import Client
from embykeeper.config import config
from embykeeper.telegram.session import API_ID, API_HASH

app = AsyncTyper()


async def dump(client: Client, message: Message):
    if message.text:
        logger.debug(f"<- {message.text}")


async def send_signin_link(client: Client, message: Message):
    markup = InlineKeyboardMarkup(
        [[InlineKeyboardButton("签到", url="https://t.me/HiEmbyBot/SignIn?startapp=123456789")]]
    )
    await message.reply("请在一分钟内点击下方按钮完成签到", reply_markup=markup)


async def send_success_message(client: Client, message: Message):
    await message.reply("🎉签到成功\n\n恭喜您获得了1枚金币，您目前拥有2枚!")


@app.async_command()
async def main(config_file: Path):
    await config.reload_conf(config_file)
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
        await bot.add_handler(MessageHandler(send_signin_link, filters.command("hi")))
        await bot.add_handler(MessageHandler(send_success_message, filters.command("success")))
        await bot.set_bot_commands(
            [
                BotCommand("hi", "Send signin link"),
                BotCommand("success", "Show success message"),
            ]
        )
        logger.info(f"Started listening for commands: @{bot.me.username}.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    app()
