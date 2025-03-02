import asyncio
from pathlib import Path
import random
from textwrap import dedent

from loguru import logger
import tomli as tomllib
from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import (
    Message,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)
from pyrogram.enums import ParseMode

from embykeeper.utils import AsyncTyper
from embykeeper.telegram.pyrogram import Client
from embykeeper.config import config
from embykeeper.telegram.session import API_ID, API_HASH

app = AsyncTyper()

states = {}
signed = {}

main_photo = Path(__file__).parent / "data/main.png"
main_reply_markup = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="️👥 用户功能", callback_data="members"),
            InlineKeyboardButton(text="🌐 服务器", callback_data="server"),
        ],
        [
            InlineKeyboardButton(text="🎟️ 使用注册码", callback_data="exchange"),
            InlineKeyboardButton(text="🎯 签到", callback_data="checkin"),
        ],
    ]
)


async def dump(client: Client, message: Message):
    if message.text:
        logger.debug(f"<- {message.text}")


async def start(client: Client, message: Message):
    content = dedent(
        """
    ✨ 只有你想见我的时候我们的相遇才有意义

    🍉你好鸭 ********* 请选择功能👇

    📠请在下方选择您要使用的功能!
    """.strip()
    )
    await client.send_photo(
        message.chat.id,
        main_photo,
        caption=content,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_reply_markup,
    )


async def callback_checkin(client: Client, callback: CallbackQuery):
    if signed.get(callback.from_user.id, None):
        await callback.answer("您今天已经签到过了.")
        return

    operation = random.choice(["+", "-", "×", "÷"])
    if operation == "+":
        num1 = random.randint(1, 99)
        num2 = random.randint(1, 99)
        result = num1 + num2
    elif operation == "-":
        num1 = random.randint(2, 99)
        num2 = random.randint(1, num1)
        result = num1 - num2
    elif operation == "×":
        num1 = random.randint(1, 10)
        num2 = random.randint(1, 10)
        result = num1 * num2
    elif operation == "÷":
        num2 = random.randint(1, 10)
        result = random.randint(1, 10)
        num1 = num2 * result

    states[callback.from_user.id] = str(result)
    content = dedent(
        f"""
    🎯 签到说明：

    在120s内计算出 {num1} {operation} {num2} = ?
    结果正确你将会随机获得6 ~ 18 硬币(概率获得88 硬币)
    结果错误你将会随机扣除6 ~ 18 硬币(概率扣除88 硬币), 请谨慎回答
    """
    ).strip()
    await client.send_photo(
        chat_id=callback.message.chat.id,
        photo=main_photo,
        caption=content,
        parse_mode=ParseMode.MARKDOWN,
    )
    await callback.answer()


async def result(client: Client, message: Message):
    r = message.text
    if r == states.get(message.from_user.id, None):
        signed[message.from_user.id] = True
        content = dedent(
            """
        🎉 签到完成 | 本次签到你获得了 14 硬币
        💴 当前硬币余额 | 184
        ⏳ 签到日期 | 2024-07-08
        """.strip()
        )
        await client.send_photo(
            message.chat.id,
            main_photo,
            caption=content,
            parse_mode=ParseMode.MARKDOWN,
        )


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
        await bot.add_handler(CallbackQueryHandler(callback_checkin, filters.regex("checkin")))
        await bot.add_handler(MessageHandler(result))
        await bot.set_bot_commands(
            [
                BotCommand("start", "Start the bot"),
            ]
        )
        logger.info(f"Started listening for commands: @{bot.me.username}.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    app()
