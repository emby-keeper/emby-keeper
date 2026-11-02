"""Persistence for panel-level JSON documents.

With ``EK_MONGODB`` set the panel keeps no durable files: settings and the KV
store live in MongoDB, so containers without a persistent volume can be
recreated without losing state.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

MONGODB_ENV = "EK_MONGODB"
MONGODB_DATABASE = "embykeeper"
PANEL_COLLECTION = "panel"


def mongodb_url() -> Optional[str]:
    url = os.environ.get(MONGODB_ENV, "").strip()
    return url or None


def _brief(exc: Exception, limit: int = 160) -> str:
    text = str(exc).replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "..."


def check_mongodb(url: Optional[str] = None, timeout_ms: int = 5000) -> None:
    """Raise RuntimeError if the configured MongoDB cannot be reached."""

    url = url if url is not None else mongodb_url()
    if not url:
        return
    from pymongo import MongoClient

    client = MongoClient(url, serverSelectionTimeoutMS=timeout_ms)
    try:
        client.admin.command("ping")
    except Exception as exc:
        raise RuntimeError(f"MongoDB 连接失败: {exc}") from exc


class JsonDocumentStore:
    """Stores one JSON document per id, in a local file or MongoDB."""

    def __init__(
        self,
        path: Path,
        doc_id: str,
        url: Optional[str] = None,
        collection=None,
    ):
        self.path = Path(path)
        self.doc_id = doc_id
        self._collection = collection
        if self._collection is None:
            url = url if url is not None else mongodb_url()
            if url:
                from pymongo import MongoClient

                self._client = MongoClient(url, serverSelectionTimeoutMS=5000)
                self._collection = self._client[MONGODB_DATABASE][PANEL_COLLECTION]

    @property
    def mongo(self) -> bool:
        return self._collection is not None

    def describe(self) -> str:
        if self.mongo:
            return f"MongoDB ({MONGODB_DATABASE}.{PANEL_COLLECTION}/{self.doc_id})"
        return str(self.path)

    def check(self) -> None:
        if self._collection is not None:
            self._collection.database.client.admin.command("ping")

    def load(self) -> Optional[Dict[str, Any]]:
        if self.mongo:
            doc = self._collection.find_one({"_id": self.doc_id})
            if not doc:
                return self._import_legacy_file()
            value = doc.get("value")
            return value if isinstance(value, dict) else None
        payload = self._read_file()
        return payload

    def _read_file(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None
        with open(self.path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        return payload if isinstance(payload, dict) else None

    def _import_legacy_file(self) -> Optional[Dict[str, Any]]:
        """Move state written by an earlier file-based deployment into MongoDB."""

        try:
            payload = self._read_file()
        except (OSError, ValueError) as exc:
            logger.warning(f'读取 "{self.path}" 失败, 未导入 MongoDB: {_brief(exc)}')
            return None
        if payload is None:
            return None
        try:
            self.save(payload)
            self.path.rename(self.path.with_suffix(self.path.suffix + ".migrated"))
        except Exception as exc:
            logger.warning(f'导入 "{self.path}" 到 MongoDB 失败: {_brief(exc)}')
            return None
        logger.info(f'已将 "{self.path}" 中的面板状态导入 MongoDB.')
        return payload

    def save(self, data: Dict[str, Any]) -> None:
        if self.mongo:
            self._collection.update_one({"_id": self.doc_id}, {"$set": {"value": data}}, upsert=True)
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
