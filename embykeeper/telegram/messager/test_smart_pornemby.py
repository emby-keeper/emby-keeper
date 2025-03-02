from datetime import time

from .smart_pornemby import SmartPornembyMessager

__ignore__ = True


class TestSmartPornembyMessager(SmartPornembyMessager):
    name = "Pornemby 智能水群测试"
    chat_name = "api_group"
    msg_per_day = 1000
    min_msg_gap = 0
    at = (time(0, 0), time(23, 59))
