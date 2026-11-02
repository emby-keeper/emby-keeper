"""Where the whole configuration document lives.

The default source is a local TOML file. A MongoDB source is used for
deployments without a persistent volume (panel mode with ``EK_MONGODB``), which
stores the same document as base64 encoded TOML so it stays compatible with the
legacy console.
"""

import base64
import binascii
from pathlib import Path
from typing import Any, Dict, Optional

import tomli as tomllib
import tomlkit

MONGODB_DATABASE = "embykeeper"
CONFIG_COLLECTION = "cache"
CONFIG_DOC_ID = "config"


class ConfigSourceError(Exception):
    """Raised when a config source cannot be read or written."""


def encode_config(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def decode_config(data: str) -> str:
    try:
        return base64.b64decode("".join(str(data).split()).encode()).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ConfigSourceError(f"配置数据格式错误: {exc}") from exc


class ConfigSource:
    """Reads and writes the whole configuration document."""

    def read(self) -> Dict[str, Any]:
        raise NotImplementedError

    def write(self, cfg: Dict[str, Any]) -> None:
        raise NotImplementedError

    def describe(self) -> str:
        raise NotImplementedError

    def check(self) -> None:
        """Raise ConfigSourceError if the backend cannot be used."""


class FileConfigSource(ConfigSource):
    def __init__(self, path):
        self.path = Path(path)

    def describe(self) -> str:
        return str(self.path)

    def check(self) -> None:
        parent = self.path.parent
        try:
            parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ConfigSourceError(f'配置目录 "{parent}" 不可用: {exc}') from exc

    def read(self) -> Dict[str, Any]:
        if not self.path.exists():
            return {}
        try:
            with open(self.path, "rb") as f:
                return tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigSourceError(f'配置文件 "{self.path}" 中的 TOML 格式错误: {exc}') from exc
        except OSError as exc:
            raise ConfigSourceError(f'无法读取配置文件 "{self.path}": {exc}') from exc

    def write(self, cfg: Dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(tomlkit.dumps(cfg))
        except OSError as exc:
            raise ConfigSourceError(f'无法写入配置文件 "{self.path}": {exc}') from exc


class MongoConfigSource(ConfigSource):
    def __init__(self, url: str, collection=None):
        self._collection = collection
        if self._collection is not None:
            return
        try:
            from pymongo import MongoClient
        except ImportError as exc:
            raise ConfigSourceError("未安装 pymongo, 无法使用 MongoDB 存储配置.") from exc
        self._client = MongoClient(url, serverSelectionTimeoutMS=5000)
        self._collection = self._client[MONGODB_DATABASE][CONFIG_COLLECTION]

    def describe(self) -> str:
        return f"MongoDB ({MONGODB_DATABASE}.{CONFIG_COLLECTION})"

    def check(self) -> None:
        try:
            self._collection.database.client.admin.command("ping")
        except Exception as exc:
            raise ConfigSourceError(f"MongoDB 连接失败: {exc}") from exc

    def read(self) -> Dict[str, Any]:
        try:
            doc = self._collection.find_one({"_id": CONFIG_DOC_ID})
        except Exception as exc:
            raise ConfigSourceError(f"从 MongoDB 读取配置失败: {exc}") from exc
        if not doc or not doc.get("value"):
            return {}
        text = decode_config(doc["value"])
        try:
            return tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise ConfigSourceError(f"MongoDB 中的配置格式错误: {exc}") from exc

    def write(self, cfg: Dict[str, Any]) -> None:
        value = encode_config(tomlkit.dumps(cfg))
        try:
            self._collection.update_one({"_id": CONFIG_DOC_ID}, {"$set": {"value": value}}, upsert=True)
        except Exception as exc:
            raise ConfigSourceError(f"向 MongoDB 写入配置失败: {exc}") from exc

    def cache_empty(self) -> bool:
        try:
            return self._collection.find_one({"_id": {"$ne": CONFIG_DOC_ID}}) is None
        except Exception as exc:
            raise ConfigSourceError(f"从 MongoDB 读取缓存失败: {exc}") from exc

    def import_cache(self, items: Dict[str, Any]) -> int:
        for key, value in items.items():
            self._collection.update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)
        return len(items)


def mongodb_url() -> Optional[str]:
    import os

    url = os.environ.get("EK_MONGODB", "").strip()
    return url or None
