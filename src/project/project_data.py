"""Project data models for openRetop project files."""

from __future__ import annotations

from dataclasses import dataclass, field


PROJECT_VERSION = 1


@dataclass
class ProjectTransform:
    location: list[float]
    rotation: list[float]
    scale: float
    origin: list[float]


@dataclass
class ProjectDisplaySettings:
    proxy_quality: str
    show_grid: bool
    show_axes: bool
    show_normals: bool


@dataclass
class ProjectSectionSettings:
    axis: str
    offset: float
    show_plane: bool


@dataclass
class ProjectSectionPlane:
    id: str
    name: str
    axis: str
    offset: float
    visible: bool


@dataclass
class ProjectSectionResult:
    id: str
    name: str
    plane_id: str
    axis: str
    offset: float
    visible: bool
    polylines: list[list[list[float]]]
    segment_count: int


@dataclass
class ProjectCurve:
    id: str
    name: str
    section_result_id: str
    plane_id: str
    original_points: list[list[float]]
    fitted_points: list[list[float]]
    mean_error: float
    max_error: float
    is_closed: bool
    visible: bool


@dataclass
class ProjectSurface:
    id: str
    name: str
    source_curve_ids: list[str]
    surface_type: str
    visible: bool
    metadata: dict[str, object]


@dataclass
class ProjectData:
    version: int
    name: str
    mesh_path: str | None
    transform: ProjectTransform
    display: ProjectDisplaySettings
    section: ProjectSectionSettings
    section_planes: list[ProjectSectionPlane] = field(default_factory=list)
    active_section_plane_id: str | None = None
    mesh_name: str | None = None
    mesh_visible: bool = True
    section_results: list[ProjectSectionResult] = field(default_factory=list)
    curves: list[ProjectCurve] = field(default_factory=list)
    surfaces: list[ProjectSurface] = field(default_factory=list)


def default_project_data() -> ProjectData:
    return ProjectData(
        version=PROJECT_VERSION,
        name="Untitled Project",
        mesh_path=None,
        mesh_name=None,
        mesh_visible=True,
        transform=ProjectTransform(
            location=[0.0, 0.0, 0.0],
            rotation=[0.0, 0.0, 0.0],
            scale=1.0,
            origin=[0.0, 0.0, 0.0],
        ),
        display=ProjectDisplaySettings(
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
        ),
        section=ProjectSectionSettings(
            axis="Z",
            offset=0.0,
            show_plane=False,
        ),
    )
