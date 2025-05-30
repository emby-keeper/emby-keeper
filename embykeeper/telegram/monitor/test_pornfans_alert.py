from .pornfans_alert import PornfansAlertMonitor

__ignore__ = True


class TestPornfansAlertMonitor(PornfansAlertMonitor):
    name = "PornFans 风险急停 测试"
    chat_name = "api_group"
    chat_allow_outgoing = True
