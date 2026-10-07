"""UI-independent settings repository ports and JSON implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from openretop.project.atomic_io import write_text_atomic
from openretop.settings.settings_data import AppSettings, default_app_settings
from openretop.settings.settings_io import (
    default_settings_path,
    settings_from_dict,
    settings_to_dict,
)


@dataclass(frozen=True)
class SettingsMessage:
    code: str
    message: str


@dataclass(frozen=True)
class SettingsLoadResult:
    settings: AppSettings
    path: Path
    warnings: tuple[SettingsMessage, ...] = ()
    errors: tuple[SettingsMessage, ...] = ()
    migrated: bool = False

    @property
    def success(self) -> bool:
        return not self.errors


@dataclass(frozen=True)
class SettingsSaveResult:
    path: Path
    warnings: tuple[SettingsMessage, ...] = ()
    errors: tuple[SettingsMessage, ...] = ()

    @property
    def success(self) -> bool:
        return not self.errors


class SettingsRepository(Protocol):
    def read(self, path: str | Path | None = None) -> SettingsLoadResult:
        ...

    def write(self, settings: AppSettings, path: str | Path | None = None) -> SettingsSaveResult:
        ...


class JsonSettingsRepository:
    def read(self, path: str | Path | None = None) -> SettingsLoadResult:
        settings_path = Path(path) if path is not None else default_settings_path()
        try:
            data = json.loads(settings_path.read_text(encoding="utf-8"))
            settings = settings_from_dict(data)
        except FileNotFoundError:
            return SettingsLoadResult(default_app_settings(), settings_path)
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            return SettingsLoadResult(
                default_app_settings(),
                settings_path,
                warnings=(SettingsMessage("settings_defaults", "Invalid settings were replaced with defaults."),),
                errors=(SettingsMessage("invalid_settings", str(exc)),),
            )
        return SettingsLoadResult(settings, settings_path)

    def write(self, settings: AppSettings, path: str | Path | None = None) -> SettingsSaveResult:
        settings_path = Path(path) if path is not None else default_settings_path()
        try:
            write_text_atomic(
                settings_path,
                json.dumps(settings_to_dict(settings), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            )
        except (OSError, TypeError, ValueError) as exc:
            return SettingsSaveResult(
                settings_path,
                errors=(SettingsMessage("settings_write_failed", str(exc)),),
            )
        return SettingsSaveResult(settings_path)

    def load(self, path: str | Path | None = None) -> AppSettings:
        return self.read(path).settings

    def save(self, settings: AppSettings, path: str | Path | None = None) -> None:
        result = self.write(settings, path)
        if not result.success:
            raise OSError(result.errors[0].message)


class InMemorySettingsRepository:
    def __init__(self, settings: AppSettings | None = None) -> None:
        self.settings = settings or default_app_settings()

    def read(self, path: str | Path | None = None) -> SettingsLoadResult:
        return SettingsLoadResult(self.settings, Path(path) if path else Path("settings.json"))

    def write(self, settings: AppSettings, path: str | Path | None = None) -> SettingsSaveResult:
        self.settings = settings
        return SettingsSaveResult(Path(path) if path else Path("settings.json"))
