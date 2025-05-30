from .pornfans_dragon_rain import PornfansDragonRainMonitor

__ignore__ = True


class TestPornfansDragonRainMonitor(PornfansDragonRainMonitor.PornfansDragonRainClickMonitor):
    name = "PornFans 红包雨 测试"
    chat_name = "api_group"
    chat_user = "embykeeper_test_bot"
    chat_allow_outgoing = True
