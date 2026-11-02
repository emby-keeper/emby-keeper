import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .state_store import JsonDocumentStore, _brief

logger = logging.getLogger(__name__)


class KVStore:

    def __init__(self, path: Optional[str] = None, collection=None):
        if path is None:
            path = Path.home() / ".embykeeper" / "kv_store.json"
        self.path = Path(path)
        self._store = JsonDocumentStore(self.path, "kv", collection=collection)
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        try:
            payload = self._store.load()
            if payload is not None:
                self._data = payload
                logger.debug(f"KV store loaded from {self._store.describe()}")
        except Exception as e:
            logger.warning(f"Failed to load KV store: {_brief(e)}")
            self._data = {}

    def _save(self):
        try:
            self._store.save(self._data)
        except Exception as e:
            logger.error(f"Failed to save KV store: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self._save()

    def delete(self, key: str) -> bool:
        if key in self._data:
            del self._data[key]
            self._save()
            return True
        return False

    def has(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> list:
        return list(self._data.keys())

    def all(self) -> Dict[str, Any]:
        return self._data.copy()

    def clear(self) -> None:
        self._data = {}
        self._save()

    def update(self, data: Dict[str, Any]) -> None:
        self._data.update(data)
        self._save()


kv_store = KVStore()
