from .pornemby_dragon_rain import PornembyDragonRainMonitor

__ignore__ = True


class TestPornembyDragonRainMonitor(PornembyDragonRainMonitor.PornembyDragonRainClickMonitor):
    name = "Pornemby 红包雨 测试"
    chat_name = "api_group"
    chat_user = "embykeeper_test_bot"
    chat_allow_outgoing = True
