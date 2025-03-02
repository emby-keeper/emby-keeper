from .bgk import BGKMonitor

__ignore__ = True


class TestBGKMonitor(BGKMonitor):
    name = "不给看 测试"
    chat_name = "api_group"
    chat_allow_outgoing = True
    chat_user = []
