import asyncio
from pathlib import Path

from loguru import logger
from pyrogram import filters
from pyrogram.handlers import MessageHandler
from pyrogram.types import Message, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.enums import ParseMode

from embykeeper.utils import AsyncTyper
from embykeeper.telegram.pyrogram import Client
from embykeeper.telegram.session import API_ID, API_HASH
from embykeeper.config import config
from embykeeper import var

app = AsyncTyper()


async def start(client: Client, message: Message):
    # 获取 /start 命令的回复消息
    if not message.reply_to_message:
        return

    reply_msg = message.reply_to_message
    buttons = None

    # 检查是否有命令参数
    command_text = message.text.split(None, 1)
    if len(command_text) > 1:
        # 有命令参数，解析按钮
        text = command_text[1]
        if "#" in text:
            # 按##分割成不同行
            button_rows = text.split("##")

            if button_rows:
                buttons = []
                for row_text in button_rows:
                    if not row_text:  # 跳过空行
                        continue
                    # 处理每一行的按钮
                    row_buttons = []
                    for btn in row_text.split("#"):
                        if not btn:  # 跳过空按钮
                            continue
                        # 解析按钮文本和callback_data
                        if "(" in btn and ")" in btn:
                            btn_text = btn[: btn.find("(")]
                            callback_data = btn[btn.find("(") + 1 : btn.find(")")]
                            row_buttons.append(InlineKeyboardButton(btn_text, callback_data=callback_data))

                    if row_buttons:
                        buttons.append(row_buttons)

                if buttons:
                    buttons = InlineKeyboardMarkup(buttons)

    # 发送消息
    if reply_msg.photo:
        # 如果是图片，复制图片并添加caption
        await client.send_photo(
            message.chat.id,
            reply_msg.photo.file_id,
            caption=reply_msg.caption,
            reply_markup=buttons,
            parse_mode=ParseMode.MARKDOWN,
        )
    else:
        # 如果是纯文本，发送文本消息
        await client.send_message(
            message.chat.id, reply_msg.text, reply_markup=buttons, parse_mode=ParseMode.MARKDOWN
        )


@app.async_command()
async def main(config_file: Path):
    var.debug = 2
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
        await bot.add_handler(MessageHandler(start, filters.command("start")))
        logger.info(f"Started listening for commands: @{bot.me.username}.")
        await asyncio.Future()


if __name__ == "__main__":
    app()
