import asyncio

import pytest

from embykeeper.config import ConfigManager
from embykeeper.config_source import (
    FileConfigSource,
    MongoConfigSource,
    encode_config,
)
from embykeeperapi.kv import KVStore
from embykeeperapi.settings import PanelSettingsStore


@pytest.fixture(autouse=True)
def event_loop_for_imports():
    # asyncio.run() in earlier tests leaves the main thread without a loop, and
    # module-level asyncio primitives (embykeeper.var) need one when imported.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield
    loop.close()
    asyncio.set_event_loop(None)


class FakeCollection:
    """Minimal stand-in for a pymongo collection used by the sources."""

    def __init__(self):
        self.docs = {}

    def find_one(self, query):
        doc_id = query.get("_id")
        if isinstance(doc_id, dict) and "$ne" in doc_id:
            for key, doc in self.docs.items():
                if key != doc_id["$ne"]:
                    return doc
            return None
        return self.docs.get(doc_id)

    def update_one(self, query, update, upsert=False):
        doc_id = query["_id"]
        current = self.docs.get(doc_id, {"_id": doc_id})
        current.update(update.get("$set", {}))
        self.docs[doc_id] = current


def test_file_source_round_trip(tmp_path):
    source = FileConfigSource(tmp_path / "config.toml")
    assert source.read() == {}

    source.write({"emby": {"interval_days": 3}})

    assert source.read()["emby"]["interval_days"] == 3


def test_mongo_source_round_trip(tmp_path):
    collection = FakeCollection()
    source = MongoConfigSource("mongodb://unused", collection=collection)

    source.write({"checkiner": {"retries": 2}})

    assert source.read()["checkiner"]["retries"] == 2
    assert "mongodb" not in source.read()


def test_mongo_source_reads_legacy_console_document():
    collection = FakeCollection()
    collection.docs["config"] = {
        "_id": "config",
        "value": encode_config("[emby]\nconcurrency = 4\n"),
    }

    source = MongoConfigSource("mongodb://unused", collection=collection)

    assert source.read()["emby"]["concurrency"] == 4


def test_mongo_source_rejects_broken_document():
    collection = FakeCollection()
    collection.docs["config"] = {"_id": "config", "value": "not base64!"}

    source = MongoConfigSource("mongodb://unused", collection=collection)

    assert not asyncio.run(_reload(source))


async def _reload(source):
    manager = ConfigManager()
    manager.set_source(source)
    return await manager.reload_conf()


def test_config_manager_loads_config_from_source():
    collection = FakeCollection()
    collection.docs["config"] = {
        "_id": "config",
        "value": encode_config("[emby]\nconcurrency = 5\n"),
    }
    manager = ConfigManager()
    manager.set_source(MongoConfigSource("mongodb://unused", collection=collection))

    assert asyncio.run(manager.reload_conf())
    assert manager.emby.concurrency == 5
    assert manager.active_source().describe().startswith("MongoDB")


def test_panel_settings_use_mongo_collection(tmp_path):
    collection = FakeCollection()
    path = tmp_path / "settings.json"
    store = PanelSettingsStore(path=path, collection=collection)

    store.update(backend_config_file="/data/config.toml")

    assert collection.docs["settings"]["value"]["backend_config_file"] == "/data/config.toml"
    assert not path.exists()
    reopened = PanelSettingsStore(path=path, collection=collection)
    assert reopened.get().backend_config_file == "/data/config.toml"


def test_kv_store_uses_mongo_collection(tmp_path):
    collection = FakeCollection()
    path = str(tmp_path / "kv_store.json")
    store = KVStore(path=path, collection=collection)

    store.set("theme", "dark")

    assert collection.docs["kv"]["value"]["theme"] == "dark"
    assert not (tmp_path / "kv_store.json").exists()
    reopened = KVStore(path=path, collection=collection)
    assert reopened.get("theme") == "dark"


VALID_CONFIG = """
[emby]
interval_days = "<3,5>"

[[emby.account]]
url = "https://example.com"
username = "migrated"
password = "pw"
"""


def test_migrate_local_state_imports_config_and_cache(tmp_path):
    from embykeeper import cli

    collection = FakeCollection()
    source = MongoConfigSource("mongodb://unused", collection=collection)
    (tmp_path / "config.toml").write_text(VALID_CONFIG, encoding="utf-8")
    (tmp_path / "cache.json").write_text('{"telegram.session_str.a": "abc"}', encoding="utf-8")

    cli._migrate_local_state(source, basedir=tmp_path)

    assert source.read()["emby"]["account"][0]["username"] == "migrated"
    assert collection.docs["telegram.session_str.a"]["value"] == "abc"
    assert not (tmp_path / "cache.json").exists()
    assert (tmp_path / "cache.json.migrated").exists()


def test_migrate_local_state_skips_invalid_config(tmp_path):
    from embykeeper import cli

    collection = FakeCollection()
    source = MongoConfigSource("mongodb://unused", collection=collection)
    (tmp_path / "config.toml").write_text(
        '[telegram]\n[telegram.account]\nphone = "+10000000000"\n', encoding="utf-8"
    )

    cli._migrate_local_state(source, basedir=tmp_path)

    assert source.read() == {}


def test_migrate_local_state_keeps_existing_database_cache(tmp_path):
    from embykeeper import cli

    collection = FakeCollection()
    collection.docs["telegram.session_str.a"] = {"_id": "telegram.session_str.a", "value": "db"}
    source = MongoConfigSource("mongodb://unused", collection=collection)
    (tmp_path / "cache.json").write_text('{"telegram.session_str.a": "file"}', encoding="utf-8")

    cli._migrate_local_state(source, basedir=tmp_path)

    assert collection.docs["telegram.session_str.a"]["value"] == "db"
    assert (tmp_path / "cache.json").exists()


def test_panel_health_endpoint_is_public():
    from starlette.testclient import TestClient

    import embykeeperapi.app as panel_app

    with TestClient(panel_app.build_app()) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_panel_settings_import_legacy_file_once(tmp_path):
    collection = FakeCollection()
    path = tmp_path / "settings.json"
    path.write_text('{"backend_basedir": "/legacy"}', encoding="utf-8")

    store = PanelSettingsStore(path=path, collection=collection)

    assert store.get().backend_basedir == "/legacy"
    assert collection.docs["settings"]["value"]["backend_basedir"] == "/legacy"
    assert not path.exists()
    assert (tmp_path / "settings.json.migrated").exists()

    # A second start must not resurrect the file, and MongoDB stays authoritative.
    store.update(backend_basedir="/new")
    assert PanelSettingsStore(path=path, collection=collection).get().backend_basedir == "/new"


def _request_with_token(token):
    from starlette.requests import Request

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/config",
        "headers": [(b"authorization", f"Bearer {token}".encode())],
    }
    return Request(scope)


def test_login_session_survives_restart(tmp_path, monkeypatch):
    from fastapi import Response

    from embykeeperapi import auth

    monkeypatch.setenv("EK_WEBPASS", "pw")
    monkeypatch.setattr(auth, "kv_store", KVStore(path=str(tmp_path / "kv.json")))

    response = Response()
    body = asyncio.run(auth.login({"password": "pw"}, response))
    token = body["token"]
    auth.require_auth(_request_with_token(token))

    # A fresh store instance stands in for a restarted panel process.
    monkeypatch.setattr(auth, "kv_store", KVStore(path=str(tmp_path / "kv.json")))
    auth.require_auth(_request_with_token(token))


def test_expired_login_session_is_rejected(tmp_path, monkeypatch):
    from embykeeperapi import auth

    store = KVStore(path=str(tmp_path / "kv.json"))
    monkeypatch.setenv("EK_WEBPASS", "pw")
    monkeypatch.setattr(auth, "kv_store", store)
    store.set(auth.SESSION_CACHE_PREFIX + "stale", 1.0)

    with pytest.raises(Exception):
        auth.require_auth(_request_with_token("stale"))
    assert auth.SESSION_CACHE_PREFIX + "stale" not in store.keys()
