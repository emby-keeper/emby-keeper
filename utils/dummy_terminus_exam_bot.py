import asyncio
from pathlib import Path
import json
import random
import string

from loguru import logger
import tomli as tomllib
from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler
from pyrogram.types import (
    Message,
    BotCommand,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    CallbackQuery,
)

from embykeeper.utils import AsyncTyper
from embykeeper.telegram.pyrogram import Client
from embykeeper.config import config
from embykeeper.telegram.session import API_ID, API_HASH

user_states = {}
app = AsyncTyper()
questions = []


async def dump(client: Client, message: Message):
    if message.text:
        logger.debug(f"<- {message.text}")


async def start(client: Client, message: Message):
    await client.send_message(message.from_user.id, "你好! 请使用 /exam 命令开始考试!")


async def exam(client: Client, message: Message):
    global questions
    user_id = message.from_user.id

    # Initialize user state
    user_states[user_id] = {"waiting_for_exam_choice": True}

    # Send initial exam information
    initial_message = (
        "通过考核才能注册 Emby 公益服账号或继续使用账号，是否开始考核？ ( 本次考核需要消耗 40 积分 )"
    )
    keyboard = ReplyKeyboardMarkup([["✅ 开始", "🚫 放弃"]], resize_keyboard=True, one_time_keyboard=True)
    await client.send_message(user_id, initial_message, reply_markup=keyboard)


async def handle_exam_choice(client: Client, message: Message):
    user_id = message.from_user.id

    if user_id not in user_states or not user_states[user_id].get("waiting_for_exam_choice"):
        await client.send_message(user_id, "请先使用 /exam 命令开始考试。")
        return

    choice = message.text

    if choice == "✅ 开始":
        # Send exam start message
        start_message = (
            "考核开始，限时 20 分钟，90 分及格，你可以随时使用 /cancel 命令放弃考核，"
            "但每次考核间隔需大于 72 个小时 ( 如果选项按钮显示不全，请把手机横过来或使用电脑作答 )"
        )
        await client.send_message(user_id, start_message, reply_markup=ReplyKeyboardRemove())

        # Initialize user state and start the exam
        user_states[user_id].update(
            {"current_question": 0, "score": 0, "start_time": message.date, "waiting_for_exam_choice": False}
        )
        await send_question(client, user_id)
    elif choice == "🚫 放弃":
        await client.send_message(user_id, "考核已取消。", reply_markup=ReplyKeyboardRemove())
        del user_states[user_id]
    else:
        await client.send_message(user_id, "无效的选择，请重新开始考核。", reply_markup=ReplyKeyboardRemove())
        del user_states[user_id]


async def send_question(client: Client, user_id):
    global questions
    if user_id not in user_states:
        await client.send_message(user_id, "考试已结束或尚未开始。请使用 /exam 命令开始新的考试。")
        return

    state = user_states[user_id]
    if state["current_question"] >= len(questions):
        await end_exam(client, user_id)
        return

    question = questions[state["current_question"]]

    # Randomize the order of choices and generate unique IDs
    choices = [(generate_random_id(), option) for option in question["choices"]]
    random.shuffle(choices)

    # Store the mapping of IDs to choices for later verification
    state["current_choices"] = {id: option for id, option in choices}

    keyboard = [[InlineKeyboardButton(option, callback_data=f"exam-{id}")] for id, option in choices]
    reply_markup = InlineKeyboardMarkup(keyboard)

    text = f"{question['question']}\n\n本题贡献者: @测试题库\n\n进度: {state['current_question'] + 1}/{len(questions)}  |  当前分数: {state['score']}"

    if "message_id" not in state:
        message = await client.send_message(user_id, text, reply_markup=reply_markup)
        state["message_id"] = message.id
    else:
        await client.edit_message_text(user_id, state["message_id"], text, reply_markup=reply_markup)


async def handle_answer(client: Client, callback_query: CallbackQuery):
    global questions
    user_id = callback_query.from_user.id

    if user_id not in user_states:
        await callback_query.answer("考试已结束或尚未开始。请使用 /exam 命令开始新的考试。", show_alert=True)
        return

    state = user_states[user_id]
    if "current_question" not in state or state["current_question"] >= len(questions):
        await callback_query.answer("当前没有活动的问题。考试可能已经结束。", show_alert=True)
        return

    question = questions[state["current_question"]]

    selected_id = callback_query.data.split("-")[1]
    if selected_id not in state.get("current_choices", {}):
        await callback_query.answer("无效的选项。请重新选择。", show_alert=True)
        return

    selected_answer = state["current_choices"][selected_id]
    is_correct = selected_answer == question["correct_answer"]

    if is_correct:
        state["score"] += 3
        feedback = "✅ 正确"
    else:
        feedback = "❌ 错误"

    await callback_query.answer(feedback, show_alert=False)

    state["current_question"] += 1
    await send_question(client, user_id)


async def end_exam(client: Client, user_id):
    state = user_states[user_id]
    score = state["score"]
    passed = score >= 90
    result_text = f"考试结束！\n\n成绩 {score} 分，考核{'通过' if passed else '失败'}，{'恭喜你通过考核！' if passed else '需要 90 分才能及格'}"

    await client.edit_message_text(user_id, state["message_id"], result_text, reply_markup=None)
    del user_states[user_id]


def load_exam_questions():
    json_path = Path(__file__).parent / "data" / "terminus" / "exam.json"
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"Exam questions file not found: {json_path}")
        return []
    except json.JSONDecodeError:
        logger.error(f"Invalid JSON in exam questions file: {json_path}")
        return []


def generate_random_id():
    return "".join(random.choices(string.ascii_letters + string.digits, k=32))


@app.async_command()
async def main(config_file: Path):
    global questions
    questions = load_exam_questions()
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
        await bot.add_handler(MessageHandler(exam, filters.command("exam")))
        await bot.add_handler(MessageHandler(handle_exam_choice, filters.regex(r"^(✅ 开始|🚫 放弃)$")))
        await bot.add_handler(CallbackQueryHandler(handle_answer, filters.regex(r"^exam-")))
        await bot.set_bot_commands(
            [
                BotCommand("start", "Start the bot"),
                BotCommand("exam", "Start the exam"),
            ]
        )
        logger.info(f"Started listening for commands: @{bot.me.username}.")
        await asyncio.Event().wait()


if __name__ == "__main__":
    app()
