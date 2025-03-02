from .shufu import ShufuMonitor

__ignore__ = True


class TestShufuMonitor(ShufuMonitor):
    name = "Shufu 测试"
    chat_name = "api_group"
    chat_allow_outgoing = True
