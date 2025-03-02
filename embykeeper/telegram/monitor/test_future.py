from .future import FutureMonitor

__ignore__ = True


class TestFutureMonitor(FutureMonitor):
    name = "未响 测试"
    chat_name = "api_group"
    chat_allow_outgoing = True
    chat_user = []
