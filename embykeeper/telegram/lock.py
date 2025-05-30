import asyncio

from cachetools import TTLCache

ocrs = TTLCache(maxsize=1024, ttl=3600)  # spec: (DdddOcr, bool)
ocrs_lock = asyncio.Lock()

misty_monitors = {}  # uid: MistyMonitor
misty_locks = {}  # uid: lock

pornfans_nohp = {}  # uid: date
pornfans_messager_enabled = {}  # uid: bool
pornfans_alert = {}  # uid: bool
pornfans_messager_mids = {}  # uid: list(mid)
pornfans_messager_mids_lock = asyncio.Lock()

super_ad_shown = {}  # uid: bool
super_ad_shown_lock = asyncio.Lock()

authed_services = {}  # uid: {service: bool}
authed_services_lock = asyncio.Lock()
