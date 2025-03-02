import asyncio
from io import BytesIO
from pathlib import Path
import random
import string

from loguru import logger
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message, BotCommand
from captcha.image import ImageCaptcha

from embykeeper.config import config
from embykeeper.telegram.session import API_ID, API_HASH
from embykeeper.utils import AsyncTyper
from embykeeper.telegram.pyrogram import Client

user_states = {}

app = AsyncTyper()


async def dump(client: Client, message: Message):
    if message.text:
        logger.debug(f"<- {message.text}")


async def start(client: Client, message: Message):
    await client.send_message(message.from_user.id, "你好! 请使用命令进行签到测试!")


async def check_captcha(client: Client, message: Message):
    if message.from_user.id not in user_states:
        await message.reply("未知输入")
    else:
        if user_states[message.from_user.id].lower() == message.text.lower():
            del user_states[message.from_user.id]
            await message.reply("成功")
        else:
            await message.reply("失败")


async def send_captcha(client: Client, message: Message):
    code = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(3))
    user_states[message.from_user.id] = code
    stream = BytesIO()
    ImageCaptcha().write(code, stream)
    await client.send_photo(message.from_user.id, stream)


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
        await bot.add_handler(MessageHandler(start, filters.command("start")))
        await bot.add_handler(MessageHandler(send_captcha, filters.command("checkin")))
        await bot.add_handler(MessageHandler(check_captcha, filters.text))
        await bot.set_bot_commands(
            [
                BotCommand("start", "Start the bot"),
                BotCommand("checkin", "Checkin session for test"),
            ]
        )
        logger.info(f"Started listening for commands: @{bot.me.username}.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    app()
