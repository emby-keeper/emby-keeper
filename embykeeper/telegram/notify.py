import logging

from loguru import logger

from embykeeper.log import formatter
from embykeeper.config import config

from .log import TelegramStream

logger = logger.bind(scheme="telegram")


async def start_notifier():
    """消息通知初始化函数."""

    def _filter_log(record):
        notify = record.get("extra", {}).get("log", None)
        if notify or record["level"].no == logging.ERROR:
            return True
        else:
            return False

    def _filter_msg(record):
        notify = record.get("extra", {}).get("msg", None)
        if notify:
            return True
        else:
            return False

    def _formatter(record):
        return "{level}#" + formatter(record)

    accounts = config.telegram.account
    notifier = config.notifier
    if notifier:
        account = None
        if notifier.enabled:
            if isinstance(notifier.account, int):
                try:
                    account = accounts[notifier.account - 1]
                except IndexError:
                    notifier = None
            elif isinstance(notifier, str):
                for a in accounts:
                    if a["phone"] == notifier:
                        account = a
                        break

    if account:
        logger.info(f'计划任务的关键消息将通过 Embykeeper Bot 发送至 "{account.phone}" 账号.')
        stream_log = TelegramStream(
            account=account,
            instant=config.notifier.immediately,
        )
        logger.add(
            stream_log,
            format=_formatter,
            filter=_filter_log,
        )
        stream_msg = TelegramStream(
            account=account,
            instant=True,
        )
        logger.add(
            stream_msg,
            format=_formatter,
            filter=_filter_msg,
        )
        return stream_log, stream_msg
    else:
        return None
