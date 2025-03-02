from .pornemby_answer import _PornembyAnswerAnswerMonitor, _PornembyAnswerResultMonitor

__ignore__ = True


class TestPornembyAnswerMonitor:
    class _TestPornembyAnswerAnswerMonitor(_PornembyAnswerAnswerMonitor):
        name = "Pornemby 问题回答测试"
        chat_name = "api_group"
        chat_user = ["embykeeper_test_bot"]

    class _TestPornembyAnswerResultMonitor(_PornembyAnswerResultMonitor):
        name = "Pornemby 问题答案测试"
        chat_name = "api_group"
        chat_user = ["embykeeper_test_bot"]
