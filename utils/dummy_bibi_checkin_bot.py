import asyncio
from pathlib import Path
import random
from textwrap import dedent
from datetime import datetime, timedelta

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

from embykeeper.cli import AsyncTyper
from embykeeper.telegram.pyrogram import Client
from embykeeper.config import config
from embykeeper.telegram.session import API_ID, API_HASH

app = AsyncTyper()

states = {}  # Store verification states
timers = {}  # Store verification timers
signed = {}  # Store signed status
original_messages = {}  # Store original message references

main_photo = Path(__file__).parent / "data/main.png"
main_reply_markup = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="👥 用户功能", callback_data="members"),
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
    user_id = message.from_user.id
    content = dedent(f"""
    ▎欢迎进入用户面板！Mem

    · 🆔 用户のID | {user_id}
    · 📊 当前状态 | 未注册
    · 🍒 积分BB币 | 0
    · ®️ 注册状态 | False
    · 🎫 总注册限制 | 799
    · 🎟️ 可注册席位 | 17
    """.strip())
    sent_message = await client.send_photo(
        message.chat.id,
        main_photo,
        caption=content,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_reply_markup,
    )
    # Store the original message reference
    original_messages[user_id] = sent_message


async def cancel_timer(user_id: int):
    if user_id in timers:
        timer = timers[user_id]
        if not timer.done():
            timer.cancel()
        del timers[user_id]


async def timeout_handler(client: Client, chat_id: int, user_id: int):
    await asyncio.sleep(60)  # 60 seconds timeout
    if user_id in states:  # If still waiting for answer
        del states[user_id]
        timeout_content = "❌ 签到验证超时，请重新签到"

        # Update the original message instead of sending a new one
        if user_id in original_messages:
            try:
                await original_messages[user_id].edit_caption(
                    caption=timeout_content,
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=main_reply_markup,
                )
            except Exception as e:
                logger.warning(f"Failed to update original message on timeout: {e}")
                # Fallback to sending a new message if updating fails
                await client.send_message(
                    chat_id,
                    timeout_content,
                    parse_mode=ParseMode.MARKDOWN,
                )
        else:
            # Fallback if original message reference is lost
            await client.send_message(
                chat_id,
                timeout_content,
                parse_mode=ParseMode.MARKDOWN,
            )


async def callback_checkin(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    if signed.get(user_id, None):
        await callback.answer("您今天已经签到过了.")
        return

    # Cancel any existing timer
    await cancel_timer(user_id)

    # First show the verification starting message
    start_content = dedent("""
    🎯 开始签到验证...

    系统正在生成验证问题
    请稍等...
    """.strip())

    # Update the original message
    await callback.message.edit_caption(
        caption=start_content,
        parse_mode=ParseMode.MARKDOWN,
    )

    # Wait for a moment
    await asyncio.sleep(2)

    # Generate a simple addition problem
    num1 = random.randint(1, 10)
    num2 = random.randint(1, 10)
    num3 = random.randint(1, 10)
    result = num1 + num2 + num3

    states[user_id] = str(result)
    question_content = dedent(f"""
    🎯 签到验证

    · ❓ 验证问题 | {num1} + {num2} + {num3} = ?
    · ⏰ 剩余时间 | 60秒
    · 💰 奖励说明 |
      答对：随机获得 10-30 BB币
      答错：扣除 5-15 BB币

    请直接发送答案数字
    """.strip())

    # Edit message to show the actual question
    await callback.message.edit_caption(
        caption=question_content,
        parse_mode=ParseMode.MARKDOWN,
    )

    # Start timeout timer
    timers[user_id] = asyncio.create_task(timeout_handler(client, callback.message.chat.id, user_id))

    await callback.answer()


async def result(client: Client, message: Message):
    user_id = message.from_user.id
    if user_id not in states:
        return

    # Delete user's message
    try:
        await message.delete()
    except Exception as e:
        logger.warning(f"Failed to delete user message: {e}")

    await cancel_timer(user_id)  # Cancel timeout timer

    answer = message.text
    correct_answer = states[user_id]
    del states[user_id]

    if answer == correct_answer:
        coins = random.randint(10, 30)
        signed[user_id] = True
        content = dedent(f"""
        ✅ 签到成功！

        · 🎉 获得BB币 | +{coins}
        · 💰 当前BB币 | {coins}
        · ⏰ 签到时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        · 📅 下次签到 | {(datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')}
        """.strip())
    else:
        coins = random.randint(5, 15)
        content = dedent(f"""
        ❌ 回答错误！

        · 😢 扣除BB币 | -{coins}
        · 💰 当前BB币 | 0
        · ⏰ 操作时间 | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """.strip())

    # Update the original message instead of sending a new one
    if user_id in original_messages:
        try:
            await original_messages[user_id].edit_caption(
                caption=content,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_reply_markup,
            )
        except Exception as e:
            logger.warning(f"Failed to update original message: {e}")
            # Fallback to sending a new message if updating fails
            await client.send_photo(
                message.chat.id,
                main_photo,
                caption=content,
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=main_reply_markup,
            )
    else:
        # Fallback if original message reference is lost
        await client.send_photo(
            message.chat.id,
            main_photo,
            caption=content,
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_reply_markup,
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
