"""Data models for persistent openRetop application settings."""

from __future__ import annotations

from dataclasses import dataclass, field

from mesh.display_proxy import DEFAULT_PROXY_QUALITY


SETTINGS_VERSION = 1
DEFAULT_REGION_SELECTION_COLOR = "#00D1FF"
DEFAULT_REGION_SELECTION_EDGE_COLOR = "#E0FFFF"
DEFAULT_REGION_SELECTION_OPACITY = 0.34


@dataclass
class AppDisplaySettings:
    show_grid: bool
    show_axes: bool
    show_normals: bool
    show_axis_gizmo: bool = True
    show_viewcube: bool = True
    region_selection_color: str = DEFAULT_REGION_SELECTION_COLOR
    region_selection_edge_color: str = DEFAULT_REGION_SELECTION_EDGE_COLOR
    region_selection_opacity: float = DEFAULT_REGION_SELECTION_OPACITY


@dataclass
class AppImportSettings:
    default_proxy_quality: str


@dataclass
class AppUiSettings:
    window_width: int
    window_height: int
    window_mode: str = "maximized"
    remember_window_size: bool = True


@dataclass
class AppKeybindSettings:
    undo: str
    redo: str
    rename_selected: str
    toggle_visibility: str
    isolate_selected: str
    show_all: str
    frame_selected: str
    move: str
    rotate: str
    confirm_transform: str
    cancel_transform: str
    delete_selected: str


@dataclass
class AppSettings:
    version: int
    display: AppDisplaySettings
    import_settings: AppImportSettings
    ui: AppUiSettings
    keybinds: AppKeybindSettings
    future: dict[str, object] = field(default_factory=dict)


def default_app_settings() -> AppSettings:
    return AppSettings(
        version=SETTINGS_VERSION,
        display=AppDisplaySettings(
            show_grid=True,
            show_axes=True,
            show_normals=False,
            show_axis_gizmo=True,
            show_viewcube=True,
            region_selection_color=DEFAULT_REGION_SELECTION_COLOR,
            region_selection_edge_color=DEFAULT_REGION_SELECTION_EDGE_COLOR,
            region_selection_opacity=DEFAULT_REGION_SELECTION_OPACITY,
        ),
        import_settings=AppImportSettings(
            default_proxy_quality=DEFAULT_PROXY_QUALITY,
        ),
        ui=AppUiSettings(
            window_width=1280,
            window_height=800,
            window_mode="maximized",
            remember_window_size=True,
        ),
        keybinds=AppKeybindSettings(
            undo="Ctrl+Z",
            redo="Ctrl+Y",
            rename_selected="F2",
            toggle_visibility="H",
            isolate_selected="Shift+H",
            show_all="Alt+H",
            frame_selected="F",
            move="G",
            rotate="R",
            confirm_transform="Enter",
            cancel_transform="Esc",
            delete_selected="Delete",
        ),
    )
