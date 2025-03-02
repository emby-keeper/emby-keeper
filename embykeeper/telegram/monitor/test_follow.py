from . import Monitor

__ignore__ = True


class TestFollowMonitor(Monitor):
    name = "从众 测试"
    chat_name = "api_group"
    chat_allow_outgoing = True
    chat_keyword = r"从众"
    chat_follow_user = 3
    chat_delay = 1
    chat_reply = "我来"
