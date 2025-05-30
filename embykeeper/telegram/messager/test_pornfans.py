from .pornfans import PornfansMessager

__ignore__ = True


class TestPornfansMessager(PornfansMessager):
    name = "PornFans 水群测试"
    chat_name = "api_group"
    default_messages = ["pornfans-common-wl@latest.yaml * 1000"]
