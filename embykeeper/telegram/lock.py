import asyncio

from cachetools import TTLCache

ocrs = TTLCache(maxsize=1024, ttl=3600)  # spec: (DdddOcr, bool)
ocrs_lock = asyncio.Lock()

misty_monitors = {}  # uid: MistyMonitor
misty_locks = {}  # uid: lock

pornemby_nohp = {}  # uid: date
pornemby_messager_enabled = {}  # uid: bool
pornemby_alert = {}  # uid: bool
pornemby_messager_mids = {}  # uid: list(mid)

super_ad_shown = {}  # uid: bool
super_ad_shown_lock = asyncio.Lock()

authed_services = {}  # uid: {service: bool}
authed_services_lock = asyncio.Lock()
