from .pornemby_nohp import PornembyNoHPMonitor

__ignore__ = True


class TestPornembyNoHPMonitor(PornembyNoHPMonitor):
    name = "Pornemby 血量耗尽停止发言 测试"
    chat_name = "api_group"
    chat_user = "embykeeper_test_bot"
    chat_allow_outgoing = True
