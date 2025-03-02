from .misty import MistyCheckin

__ignore__ = True


class TestMistyCheckin(MistyCheckin):
    ocr = None

    name = "Misty 签到测试"
    bot_username = "embykeeper_test_bot"
