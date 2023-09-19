from loguru import logger

from .base import BotCheckin

class TembyCheckin(BotCheckin):
    name = "Temby"
    bot_username = "HiEmbyBot"
    bot_checkin_cmd = "/hi"
    bot_text_ignore = ["签到成功", "恭喜您获得了", "您今天已经签到过啦，明天再来吧！"]
