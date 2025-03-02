import asyncio
from pathlib import Path
import random
from textwrap import dedent
from datetime import datetime

from loguru import logger
import tomli as tomllib
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import (
    Message,
    BotCommand,
    ReplyKeyboardMarkup,
)
from pyrogram.enums import ParseMode
from captcha.image import ImageCaptcha

from embykeeper.utils import AsyncTyper
from embykeeper.telegram.pyrogram import Client
from embykeeper.config import config
from embykeeper.telegram.session import API_ID, API_HASH

app = AsyncTyper()

states = {}
signed = {}

main_photo = Path(__file__).parent / "data/cc/main.jpg"
main_reply_markup = ReplyKeyboardMarkup(
    [
        ["⚡️账号功能", "🎲更多功能"],
        ["🚀查看线路", "🤪常见问题"],
    ],
    resize_keyboard=True,
)

more_reply_markup = ReplyKeyboardMarkup(
    [
        ["🎟我的积分", "🛎每日签到", "🎭邀请用户"],
        ["🏠返回主菜单"],
    ],
    resize_keyboard=True,
)


async def dump(client: Client, message: Message):
    if message.text:
        logger.debug(f"<- {message.text}")


async def start(client: Client, message: Message):
    # Clear captcha state if exists
    if message.from_user.id in states:
        del states[message.from_user.id]

    content = dedent(
        """
    🍉欢迎使用 Misty Bot!

    📠请在下方选择您要使用的功能!

    ⚡️有任何问题请先查看 '常见问题'!
    """.strip()
    )
    await client.send_photo(
        message.chat.id,
        main_photo,
        caption=content,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_reply_markup,
    )


async def handle_more_functions(client: Client, message: Message):
    # Clear captcha state if exists
    if message.from_user.id in states:
        del states[message.from_user.id]

    await message.reply("🎯请选择功能:", reply_markup=more_reply_markup)


async def handle_checkin(client: Client, message: Message):
    captcha = ImageCaptcha()
    captcha_text = "".join(random.choices("0123456789", k=5))
    captcha_image = captcha.generate_image(captcha_text)

    states[message.from_user.id] = captcha_text

    temp_path = Path(__file__).parent / f"temp_{message.from_user.id}.png"
    captcha_image.save(temp_path)

    await client.send_photo(message.chat.id, temp_path, caption="🤔 请输入验证码（输入 /cancel 取消）：")
    temp_path.unlink()


async def handle_captcha_response(client: Client, message: Message):
    if message.from_user.id not in states:
        return

    if message.text == states[message.from_user.id]:
        signed[message.from_user.id] = True
        current_time = datetime.now().strftime("%Y-%m-%d")
        content = dedent(
            f"""
            🎉签到成功，获得 1 积分！
            ℹ️当前积分：12
            ⏱️签到时间：{current_time}
            """.strip()
        )
        await client.send_photo(message.chat.id, main_photo, caption=content, parse_mode=ParseMode.MARKDOWN)
        await message.reply("🎯请选择功能:", reply_markup=more_reply_markup)
        del states[message.from_user.id]
    else:
        await message.reply("❌验证码错误，请重新尝试！")


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
        await bot.add_handler(MessageHandler(start, filters.command("start") | filters.command("cancel")))
        await bot.add_handler(MessageHandler(handle_more_functions, filters.regex("^🎲更多功能$")))
        await bot.add_handler(MessageHandler(handle_checkin, filters.regex("^🛎每日签到$")))
        await bot.add_handler(MessageHandler(handle_captcha_response, filters.text))
        await bot.set_bot_commands(
            [
                BotCommand("start", "Start the bot"),
            ]
        )
        logger.info(f"Started listening for commands: @{bot.me.username}.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    app()
