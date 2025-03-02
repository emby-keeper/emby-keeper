import asyncio
from pathlib import Path
import random
from datetime import datetime, timedelta

from loguru import logger
from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import Message, BotCommand, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery

from embykeeper.config import config
from embykeeper.telegram.session import API_ID, API_HASH
from embykeeper.utils import AsyncTyper
from embykeeper.telegram.pyrogram import Client

user_states = {}

app = AsyncTyper()

# Add these at the top level
CAPTCHA_CHOICES = ["灯", "情趣内衣", "报纸", "电视盒子"]
CAPTCHA_IMAGE_PATH = Path(__file__).parent / "data/terminus/captcha.jpg"

# Store today's checkins in memory
daily_checkins = set()


async def check_captcha(client: Client, callback_query: CallbackQuery):
    user_id = str(callback_query.from_user.id)

    if user_id not in user_states:
        await callback_query.answer("未知输入")
        return

    if callback_query.data not in CAPTCHA_CHOICES:
        await callback_query.answer("无效的选择")
        return

    # Log the user's choice and send success message
    logger.info(
        f"用户 {callback_query.from_user.username or user_id} 完成签到，选择了：{callback_query.data}"
    )
    await callback_query.answer()

    del user_states[user_id]


async def send_captcha(client: Client, message: Message):
    user_id = str(message.from_user.id)

    # Send captcha image and buttons
    answer = random.choice(CAPTCHA_CHOICES)
    user_states[user_id] = {"answer": answer, "expire_time": datetime.now() + timedelta(seconds=30)}

    keyboard = [[InlineKeyboardButton(choice, callback_data=choice)] for choice in CAPTCHA_CHOICES]
    reply_markup = InlineKeyboardMarkup(keyboard)

    with open(CAPTCHA_IMAGE_PATH, "rb") as photo:
        await client.send_photo(
            message.from_user.id,
            photo,
            caption="请在 30 秒内点击图中事物的按钮以完成签到",
            reply_markup=reply_markup,
        )

    # Set timeout
    asyncio.create_task(handle_timeout(client, message.from_user.id))


async def handle_timeout(client: Client, user_id: int):
    await asyncio.sleep(30)
    if str(user_id) in user_states:
        del user_states[str(user_id)]
        await client.send_message(user_id, "签到超时！")


async def dump(client: Client, message: Message):
    if message.text:
        logger.debug(f"<- {message.text}")


async def start(client: Client, message: Message):
    await client.send_message(message.from_user.id, "你好! 请使用命令进行签到测试!")


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
        await bot.add_handler(CallbackQueryHandler(check_captcha))
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
