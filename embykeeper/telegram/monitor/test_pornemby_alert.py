from .pornemby_alert import PornembyAlertMonitor

__ignore__ = True


class TestPornembyAlertMonitor(PornembyAlertMonitor):
    name = "Pornemby 风险急停 测试"
    chat_name = "api_group"
    chat_allow_outgoing = True
