"""Data models for persistent openRetop application settings."""

from __future__ import annotations

from dataclasses import dataclass, field

from mesh.display_proxy import DEFAULT_PROXY_QUALITY


SETTINGS_VERSION = 1
DEFAULT_REGION_SELECTION_COLOR = "#00D1FF"
DEFAULT_REGION_SELECTION_EDGE_COLOR = "#E0FFFF"
DEFAULT_REGION_SELECTION_OPACITY = 0.34
DEFAULT_MESH_COLOR = "#B8BDC7"
DEFAULT_SELECTED_MESH_COLOR = "#00F2FF"
DEFAULT_MANUAL_CURVE_COLOR = "#FFFFFF"
DEFAULT_SELECTED_CURVE_COLOR = "#00F2FF"
DEFAULT_ACTIVE_CURVE_COLOR = "#FFEB1F"
DEFAULT_SMOOTH_POINT_COLOR = "#F5FAFF"
DEFAULT_CORNER_POINT_COLOR = "#FF8C1F"
DEFAULT_SELECTED_POINT_COLOR = "#59F2FF"
DEFAULT_PREVIEW_POINT_COLOR = "#FF7A14"
DEFAULT_PREVIEW_LINE_COLOR = "#FF7A14"
DEFAULT_SURFACE_COLOR = "#1F577A"
DEFAULT_SELECTED_SURFACE_COLOR = "#00F2FF"
DEFAULT_BREP_SURFACE_COLOR = "#AD8A38"
DEFAULT_SELECTED_BREP_SURFACE_COLOR = "#00EBDB"
DEFAULT_BACKGROUND_COLOR = "#101316"

DISPLAY_COLOR_FIELDS = (
    "mesh_color",
    "selected_mesh_color",
    "manual_curve_color",
    "selected_curve_color",
    "active_curve_color",
    "smooth_point_color",
    "corner_point_color",
    "selected_point_color",
    "preview_point_color",
    "preview_line_color",
    "surface_color",
    "selected_surface_color",
    "brep_surface_color",
    "selected_brep_surface_color",
    "region_selection_color",
    "region_selection_edge_color",
    "background_color",
)


@dataclass
class AppDisplaySettings:
    show_grid: bool
    show_axes: bool
    show_normals: bool
    show_axis_gizmo: bool = True
    show_viewcube: bool = True
    mesh_color: str = DEFAULT_MESH_COLOR
    selected_mesh_color: str = DEFAULT_SELECTED_MESH_COLOR
    manual_curve_color: str = DEFAULT_MANUAL_CURVE_COLOR
    selected_curve_color: str = DEFAULT_SELECTED_CURVE_COLOR
    active_curve_color: str = DEFAULT_ACTIVE_CURVE_COLOR
    smooth_point_color: str = DEFAULT_SMOOTH_POINT_COLOR
    corner_point_color: str = DEFAULT_CORNER_POINT_COLOR
    selected_point_color: str = DEFAULT_SELECTED_POINT_COLOR
    preview_point_color: str = DEFAULT_PREVIEW_POINT_COLOR
    preview_line_color: str = DEFAULT_PREVIEW_LINE_COLOR
    surface_color: str = DEFAULT_SURFACE_COLOR
    selected_surface_color: str = DEFAULT_SELECTED_SURFACE_COLOR
    brep_surface_color: str = DEFAULT_BREP_SURFACE_COLOR
    selected_brep_surface_color: str = DEFAULT_SELECTED_BREP_SURFACE_COLOR
    region_selection_color: str = DEFAULT_REGION_SELECTION_COLOR
    region_selection_edge_color: str = DEFAULT_REGION_SELECTION_EDGE_COLOR
    background_color: str = DEFAULT_BACKGROUND_COLOR
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
            mesh_color=DEFAULT_MESH_COLOR,
            selected_mesh_color=DEFAULT_SELECTED_MESH_COLOR,
            manual_curve_color=DEFAULT_MANUAL_CURVE_COLOR,
            selected_curve_color=DEFAULT_SELECTED_CURVE_COLOR,
            active_curve_color=DEFAULT_ACTIVE_CURVE_COLOR,
            smooth_point_color=DEFAULT_SMOOTH_POINT_COLOR,
            corner_point_color=DEFAULT_CORNER_POINT_COLOR,
            selected_point_color=DEFAULT_SELECTED_POINT_COLOR,
            preview_point_color=DEFAULT_PREVIEW_POINT_COLOR,
            preview_line_color=DEFAULT_PREVIEW_LINE_COLOR,
            surface_color=DEFAULT_SURFACE_COLOR,
            selected_surface_color=DEFAULT_SELECTED_SURFACE_COLOR,
            brep_surface_color=DEFAULT_BREP_SURFACE_COLOR,
            selected_brep_surface_color=DEFAULT_SELECTED_BREP_SURFACE_COLOR,
            region_selection_color=DEFAULT_REGION_SELECTION_COLOR,
            region_selection_edge_color=DEFAULT_REGION_SELECTION_EDGE_COLOR,
            background_color=DEFAULT_BACKGROUND_COLOR,
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
