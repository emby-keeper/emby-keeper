from .pornfans_answer import _PornfansAnswerAnswerMonitor, _PornfansAnswerResultMonitor

__ignore__ = True


class TestPornfansAnswerMonitor:
    class _TestPornfansAnswerAnswerMonitor(_PornfansAnswerAnswerMonitor):
        name = "PornFans 问题回答测试"
        chat_name = "api_group"
        chat_user = ["embykeeper_test_bot"]

    class _TestPornfansAnswerResultMonitor(_PornfansAnswerResultMonitor):
        name = "PornFans 问题答案测试"
        chat_name = "api_group"
        chat_user = ["embykeeper_test_bot"]
