"""JSON load/save helpers for persistent application settings."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from json import JSONDecodeError
from pathlib import Path

from mesh.display_proxy import normalize_proxy_quality
from settings.settings_data import (
    SETTINGS_VERSION,
    AppDisplaySettings,
    AppImportSettings,
    AppKeybindSettings,
    AppSettings,
    AppUiSettings,
    default_app_settings,
)


SETTINGS_FILENAME = "settings.json"


def default_settings_path() -> Path:
    app_data = os.environ.get("APPDATA")
    if app_data:
        return Path(app_data) / "openRetop" / SETTINGS_FILENAME

    return Path.home() / ".config" / "openRetop" / SETTINGS_FILENAME


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    settings_path = Path(path) if path is not None else default_settings_path()
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(
        json.dumps(settings_to_dict(settings), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_settings(path: Path | None = None) -> AppSettings:
    settings_path = Path(path) if path is not None else default_settings_path()
    try:
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        return settings_from_dict(data)
    except (FileNotFoundError, OSError, JSONDecodeError, TypeError, ValueError):
        return default_app_settings()


def settings_to_dict(settings: AppSettings) -> dict[str, object]:
    if not isinstance(settings, AppSettings):
        raise ValueError("Expected AppSettings.")

    return {
        "version": int(settings.version),
        "display": {
            "show_grid": bool(settings.display.show_grid),
            "show_axes": bool(settings.display.show_axes),
            "show_normals": bool(settings.display.show_normals),
        },
        "import": {
            "default_proxy_quality": normalize_proxy_quality(
                settings.import_settings.default_proxy_quality
            ),
        },
        "ui": {
            "window_width": int(settings.ui.window_width),
            "window_height": int(settings.ui.window_height),
            "window_mode": _window_mode_value(settings.ui.window_mode, "ui.window_mode"),
            "remember_window_size": bool(settings.ui.remember_window_size),
        },
        "keybinds": {
            "rename_selected": _keybind_value(
                settings.keybinds.rename_selected,
                "keybinds.rename_selected",
            ),
            "toggle_visibility": _keybind_value(
                settings.keybinds.toggle_visibility,
                "keybinds.toggle_visibility",
            ),
            "isolate_selected": _keybind_value(
                settings.keybinds.isolate_selected,
                "keybinds.isolate_selected",
            ),
            "show_all": _keybind_value(settings.keybinds.show_all, "keybinds.show_all"),
            "frame_selected": _keybind_value(
                settings.keybinds.frame_selected,
                "keybinds.frame_selected",
            ),
            "move": _keybind_value(settings.keybinds.move, "keybinds.move"),
            "rotate": _keybind_value(settings.keybinds.rotate, "keybinds.rotate"),
            "confirm_transform": _keybind_value(
                settings.keybinds.confirm_transform,
                "keybinds.confirm_transform",
            ),
            "cancel_transform": _keybind_value(
                settings.keybinds.cancel_transform,
                "keybinds.cancel_transform",
            ),
            "delete_selected": _keybind_value(
                settings.keybinds.delete_selected,
                "keybinds.delete_selected",
            ),
        },
        "future": dict(settings.future),
    }


def settings_from_dict(data: object) -> AppSettings:
    if not isinstance(data, Mapping):
        raise ValueError("Settings data must be a dictionary.")

    defaults = default_app_settings()
    version = _settings_version(data.get("version", defaults.version))
    display_data = _optional_mapping(data.get("display"), "display")
    import_data = _optional_mapping(data.get("import"), "import")
    ui_data = _optional_mapping(data.get("ui"), "ui")
    keybind_data = _optional_mapping(data.get("keybinds"), "keybinds")
    future_data = _optional_mapping(data.get("future"), "future")

    return AppSettings(
        version=version,
        display=AppDisplaySettings(
            show_grid=_bool_value(
                _nested_value(display_data, "show_grid", defaults.display.show_grid),
                "display.show_grid",
            ),
            show_axes=_bool_value(
                _nested_value(display_data, "show_axes", defaults.display.show_axes),
                "display.show_axes",
            ),
            show_normals=_bool_value(
                _nested_value(display_data, "show_normals", defaults.display.show_normals),
                "display.show_normals",
            ),
        ),
        import_settings=AppImportSettings(
            default_proxy_quality=_proxy_quality_value(
                _nested_value(
                    import_data,
                    "default_proxy_quality",
                    defaults.import_settings.default_proxy_quality,
                ),
                "import.default_proxy_quality",
            ),
        ),
        ui=AppUiSettings(
            window_width=_positive_int_value(
                _nested_value(ui_data, "window_width", defaults.ui.window_width),
                "ui.window_width",
            ),
            window_height=_positive_int_value(
                _nested_value(ui_data, "window_height", defaults.ui.window_height),
                "ui.window_height",
            ),
            window_mode=_window_mode_value(
                _nested_value(ui_data, "window_mode", defaults.ui.window_mode),
                "ui.window_mode",
            ),
            remember_window_size=_bool_value(
                _nested_value(
                    ui_data,
                    "remember_window_size",
                    defaults.ui.remember_window_size,
                ),
                "ui.remember_window_size",
            ),
        ),
        keybinds=AppKeybindSettings(
            rename_selected=_keybind_value(
                _nested_value(
                    keybind_data,
                    "rename_selected",
                    defaults.keybinds.rename_selected,
                ),
                "keybinds.rename_selected",
            ),
            toggle_visibility=_keybind_value(
                _nested_value(
                    keybind_data,
                    "toggle_visibility",
                    defaults.keybinds.toggle_visibility,
                ),
                "keybinds.toggle_visibility",
            ),
            isolate_selected=_keybind_value(
                _nested_value(
                    keybind_data,
                    "isolate_selected",
                    defaults.keybinds.isolate_selected,
                ),
                "keybinds.isolate_selected",
            ),
            show_all=_keybind_value(
                _nested_value(keybind_data, "show_all", defaults.keybinds.show_all),
                "keybinds.show_all",
            ),
            frame_selected=_keybind_value(
                _nested_value(
                    keybind_data,
                    "frame_selected",
                    defaults.keybinds.frame_selected,
                ),
                "keybinds.frame_selected",
            ),
            move=_keybind_value(
                _nested_value(keybind_data, "move", defaults.keybinds.move),
                "keybinds.move",
            ),
            rotate=_keybind_value(
                _nested_value(keybind_data, "rotate", defaults.keybinds.rotate),
                "keybinds.rotate",
            ),
            confirm_transform=_keybind_value(
                _nested_value(
                    keybind_data,
                    "confirm_transform",
                    defaults.keybinds.confirm_transform,
                ),
                "keybinds.confirm_transform",
            ),
            cancel_transform=_keybind_value(
                _nested_value(
                    keybind_data,
                    "cancel_transform",
                    defaults.keybinds.cancel_transform,
                ),
                "keybinds.cancel_transform",
            ),
            delete_selected=_keybind_value(
                _nested_value(
                    keybind_data,
                    "delete_selected",
                    defaults.keybinds.delete_selected,
                ),
                "keybinds.delete_selected",
            ),
        ),
        future=dict(future_data) if future_data is not None else {},
    )


def _settings_version(value: object) -> int:
    version = _int_value(value, "version")
    if version != SETTINGS_VERSION:
        raise ValueError(f"Unsupported settings version: {version}")
    return version


def _optional_mapping(value: object, field_name: str) -> Mapping[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a dictionary.")
    return value


def _nested_value(
    data: Mapping[str, object] | None,
    key: str,
    default: object,
) -> object:
    if data is None:
        return default
    return data.get(key, default)


def _bool_value(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be true or false.")
    return value


def _int_value(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer.")
    return int(value)


def _positive_int_value(value: object, field_name: str) -> int:
    number = _int_value(value, field_name)
    if number <= 0:
        raise ValueError(f"{field_name} must be greater than zero.")
    return number


def _proxy_quality_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    normalized = normalize_proxy_quality(value)
    if normalized != value:
        raise ValueError(f"{field_name} must be Low, Medium, or High.")
    return normalized


def _window_mode_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    if value not in {"maximized", "remembered_size"}:
        raise ValueError(f"{field_name} must be maximized or remembered_size.")
    return value


def _keybind_value(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be a string.")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty.")
    return normalized
