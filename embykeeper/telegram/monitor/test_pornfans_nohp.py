from .pornfans_nohp import PornfansNoHPMonitor

__ignore__ = True


class TestPornfansNoHPMonitor(PornfansNoHPMonitor):
    name = "PornFans 血量耗尽停止发言 测试"
    chat_name = "api_group"
    chat_user = "embykeeper_test_bot"
    chat_allow_outgoing = True
