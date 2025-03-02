from . import Messager, MessageSchedule

__ignore__ = True


class MarmotMessager(Messager):
    name = "Marmot"
    chat_name = -1001975531465
    default_messages = [
        MessageSchedule("goodday-wl@v1.yaml", possibility=0.4, only="weekends"),
        MessageSchedule("goodnoon-wl@v2.yaml", possibility=0.1, only="weekends"),
        MessageSchedule("goodeve-wl@v1.yaml", possibility=0.1, only="weekends"),
        MessageSchedule("goodnight-wl@v1.yaml", possibility=0.4, only="weekends"),
    ]
