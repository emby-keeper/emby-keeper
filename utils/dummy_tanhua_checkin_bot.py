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
            InlineKeyboardButton(text="️👥个人信息", callback_data="info 1000000000"),
            InlineKeyboardButton(text="🌐线路信息", callback_data="line 1000000000"),
            InlineKeyboardButton(text="😵重置密码", callback_data="reset 1000000000"),
        ],
        [
            InlineKeyboardButton(text="🫣隐藏部分分类(当前: 关)", callback_data="hide 1000000000"),
        ],
    ]
)

info_reply_markup = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🎊签到", callback_data="checkin 1000000000"),
            InlineKeyboardButton(text="🏠返回主菜单", callback_data="main 1000000000"),
        ],
    ]
)

result_reply_markup = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="🏠返回主菜单", callback_data="main 1000000000"),
        ],
    ]
)

captcha_photo = Path(__file__).parent / "data/tanhua/captcha.jpg"

captcha_reply_markup = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="PFMZ", callback_data="verify_wrong_1000000000"),
            InlineKeyboardButton(text="d33u", callback_data="verify_correct_1000000000"),
        ],
        [
            InlineKeyboardButton(text="YPPC", callback_data="verify_wrong_1000000000"),
            InlineKeyboardButton(text="HTRI", callback_data="verify_wrong_1000000000"),
        ],
        [
            InlineKeyboardButton(text="🏠返回主菜单", callback_data="main 1000000000"),
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

    Jellyfin 当前用户量: 1000

    开放注册状态: 关

    🍉你好鸭 XX 请选择功能👇
    """.strip()
    )
    await client.send_photo(
        message.chat.id,
        main_photo,
        caption=content,
        reply_markup=main_reply_markup,
    )


async def callback_info(client: Client, callback: CallbackQuery):
    content = dedent(
        """
    用户名称: XXX
    绑定 tg id: 1000000000
    部分分类状态: 显示
    探花TV 启用状态: 正常
    bot 绑定时间: Thu Nov 14 10:46:20 CST 2024
    最后登录时间: 2024-01-01T00:00:00.00000Z
    最后活动时间: 2024-01-01T00:00:00.000000Z
    最后观看时间: Mon Jan 1 00:00:00 CST 2024
    积分: 0
    保号规则: 14 内有观看记录(每周五自助解封/150 积分解封)
    """
    ).strip()
    await callback.message.edit_caption(caption=content, reply_markup=info_reply_markup)
    await callback.answer()


async def callback_checkin(client: Client, callback: CallbackQuery):
    if signed.get(callback.from_user.id, None):
        await callback.message.edit_caption(caption="今日已签到", reply_markup=result_reply_markup)
    else:
        await callback.message.edit_caption(
            caption="请选择正确的验证码",
            reply_markup=captcha_reply_markup,
        )
        await client.send_photo(callback.message.chat.id, captcha_photo)
    await callback.answer()


async def callback_verify(client: Client, callback: CallbackQuery):
    if "correct" in callback.data:
        signed[callback.from_user.id] = True
        await callback.message.edit_caption(
            caption="签到获得积分: 5\n当前积分: 5", reply_markup=result_reply_markup
        )
    await callback.answer()


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
        await bot.add_handler(CallbackQueryHandler(callback_checkin, filters.regex("checkin.*")))
        await bot.add_handler(CallbackQueryHandler(callback_info, filters.regex("info.*")))
        await bot.add_handler(CallbackQueryHandler(callback_verify, filters.regex("verify_.*")))
        await bot.set_bot_commands(
            [
                BotCommand("start", "Start the bot"),
            ]
        )
        logger.info(f"Started listening for commands: @{bot.me.username}.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    app()
