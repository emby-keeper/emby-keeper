"""Panel-level settings for managing the business backend process."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

from appdirs import user_data_dir
from pydantic import BaseModel, Field, field_validator

from .state_store import JsonDocumentStore, _brief, mongodb_url

logger = logging.getLogger(__name__)

PRODUCT_NAME = "embykeeper"
SETTINGS_ENV_PATH = "EMBYKEEPERAPI_SETTINGS_PATH"
BASEDIR_ENV = "EMBYKEEPERAPI_BASEDIR"
CONFIG_FILE_ENV = "EMBYKEEPERAPI_CONFIG_FILE"


def default_backend_basedir() -> Path:
    return Path(user_data_dir(PRODUCT_NAME))


def default_settings_path() -> Path:
    return Path.home() / ".embykeeper" / "panel" / "settings.json"


class PanelSettings(BaseModel):
    """Persisted panel settings used when launching embykeeper --api."""

    backend_basedir: str = Field(
        default="",
        description="Business process working directory. Empty uses the default user data directory.",
    )
    backend_config_file: str = Field(
        default="",
        description="Business config file path. Empty uses <basedir>/config.toml.",
    )

    @field_validator("backend_basedir", "backend_config_file", mode="before")
    @classmethod
    def _normalize_optional_path(cls, value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()


class PanelSettingsStore:
    def __init__(self, path: Optional[Path] = None, collection=None):
        env_path = os.environ.get(SETTINGS_ENV_PATH)
        self.path = Path(path or env_path or default_settings_path()).expanduser()
        self._store = JsonDocumentStore(self.path, "settings", collection=collection)
        self._data = PanelSettings()
        self.reload()

    def reload(self) -> PanelSettings:
        try:
            payload = self._store.load()
        except Exception as exc:
            logger.warning(f"Failed to load panel settings: {_brief(exc)}")
            payload = None
        if payload is None:
            self._data = PanelSettings()
            return self._data
        try:
            self._data = PanelSettings(**payload)
        except (TypeError, ValueError):
            self._data = PanelSettings()
        return self._data

    def save(self, settings: PanelSettings) -> PanelSettings:
        self._store.save(settings.model_dump())
        self._data = settings
        return self._data

    def get(self) -> PanelSettings:
        return self._data

    def update(self, **kwargs: Any) -> PanelSettings:
        current = self.get().model_dump()
        current.update(kwargs)
        return self.save(PanelSettings(**current))

    def resolved_backend_basedir(self) -> Path:
        env_value = os.environ.get(BASEDIR_ENV, "").strip()
        if env_value:
            return Path(env_value).expanduser().resolve()
        configured = self.get().backend_basedir.strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return default_backend_basedir().resolve()

    def resolved_backend_config_file(self) -> Path:
        env_value = os.environ.get(CONFIG_FILE_ENV, "").strip()
        if env_value:
            return Path(env_value).expanduser().resolve()
        configured = self.get().backend_config_file.strip()
        if configured:
            return Path(configured).expanduser().resolve()
        return (self.resolved_backend_basedir() / "config.toml").resolve()

    def public_view(self) -> Dict[str, Any]:
        settings = self.get()
        basedir = self.resolved_backend_basedir()
        config_file = self.resolved_backend_config_file()
        return {
            "backend_basedir": settings.backend_basedir,
            "backend_config_file": settings.backend_config_file,
            "resolved_backend_basedir": str(basedir),
            "resolved_backend_config_file": str(config_file),
            "default_backend_basedir": str(default_backend_basedir().resolve()),
            "settings_path": str(self.path),
            "settings_storage": self._store.describe(),
            "mongodb": bool(mongodb_url()),
            "env_overrides": {
                "basedir": bool(os.environ.get(BASEDIR_ENV, "").strip()),
                "config_file": bool(os.environ.get(CONFIG_FILE_ENV, "").strip()),
            },
        }


panel_settings = PanelSettingsStore()
