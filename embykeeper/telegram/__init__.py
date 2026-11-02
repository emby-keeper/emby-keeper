from embykeeper.config import config
from embykeeper.utils import get_proxy_str


def get_telegram_proxy_config():
    try:
        if config.telegram and config.telegram.use_proxy:
            return config.proxy
    except RuntimeError:
        return None
    return None


def get_telegram_proxy_str(curl: bool = False):
    return get_proxy_str(get_telegram_proxy_config(), curl=curl)
