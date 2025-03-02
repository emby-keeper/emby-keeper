from .pornemby import PornembyMessager

__ignore__ = True


class TestPornembyMessager(PornembyMessager):
    name = "Pornemby 水群测试"
    chat_name = "api_group"
    default_messages = ["pornemby-common-wl@latest.yaml * 1000"]
