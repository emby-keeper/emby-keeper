import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class KVStore:

    def __init__(self, path: Optional[str] = None):
        if path is None:
            path = Path.home() / ".embykeeper" / "kv_store.json"
        self.path = Path(path)
        self._data: Dict[str, Any] = {}
        self._load()

    def _load(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.debug(f"KV store loaded from {self.path}")
        except Exception as e:
            logger.warning(f"Failed to load KV store: {e}")
            self._data = {}

    def _save(self):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
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
