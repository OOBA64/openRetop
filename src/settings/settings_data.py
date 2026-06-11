"""Data models for persistent openRetop application settings."""

from __future__ import annotations

from dataclasses import dataclass, field

from mesh.display_proxy import DEFAULT_PROXY_QUALITY


SETTINGS_VERSION = 1


@dataclass
class AppDisplaySettings:
    show_grid: bool
    show_axes: bool
    show_normals: bool


@dataclass
class AppImportSettings:
    default_proxy_quality: str


@dataclass
class AppUiSettings:
    window_width: int
    window_height: int


@dataclass
class AppSettings:
    version: int
    display: AppDisplaySettings
    import_settings: AppImportSettings
    ui: AppUiSettings
    future: dict[str, object] = field(default_factory=dict)


def default_app_settings() -> AppSettings:
    return AppSettings(
        version=SETTINGS_VERSION,
        display=AppDisplaySettings(
            show_grid=True,
            show_axes=True,
            show_normals=False,
        ),
        import_settings=AppImportSettings(
            default_proxy_quality=DEFAULT_PROXY_QUALITY,
        ),
        ui=AppUiSettings(
            window_width=1280,
            window_height=800,
        ),
    )
