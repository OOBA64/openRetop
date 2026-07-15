"""Project data models for openRetop project files."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import dist


PROJECT_VERSION = 1
CURVE_TINY_MIN_POINT_COUNT = 2
CURVE_TINY_MIN_LENGTH = 0.01
CURVE_TINY_MIN_BOUNDING_BOX_SIZE = 0.01


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
    colors: dict[str, str] = field(default_factory=dict)


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
    origin: list[float] | None = None
    normal: list[float] | None = None

    def __post_init__(self) -> None:
        axis = self.axis.upper()
        self.origin = _vector3_list(
            self.origin if self.origin is not None else _axis_origin(axis, self.offset)
        )
        self.normal = _vector3_list(
            self.normal if self.normal is not None else _axis_normal(axis)
        )


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
    plane_origin: list[float] | None = None
    plane_normal: list[float] | None = None
    is_arbitrary_plane: bool = False

    def __post_init__(self) -> None:
        axis = self.axis.upper()
        self.plane_origin = _vector3_list(
            self.plane_origin
            if self.plane_origin is not None
            else _axis_origin(axis, self.offset)
        )
        self.plane_normal = _vector3_list(
            self.plane_normal
            if self.plane_normal is not None
            else _axis_normal(axis)
        )
        self.is_arbitrary_plane = bool(self.is_arbitrary_plane)


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
    point_count: int | None = None
    length: float | None = None
    endpoint_distance: float | None = None
    bounding_box_size: float | None = None
    is_tiny_fragment: bool | None = None
    source_section_result_id: str | None = None
    source_plane_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.point_count is None:
            self.point_count = len(self.fitted_points)
        else:
            self.point_count = int(self.point_count)

        if self.length is None:
            self.length = _polyline_length(self.fitted_points)
        else:
            self.length = float(self.length)

        if self.endpoint_distance is None:
            self.endpoint_distance = _endpoint_distance(self.fitted_points)
        else:
            self.endpoint_distance = float(self.endpoint_distance)

        if self.bounding_box_size is None:
            self.bounding_box_size = _bounding_box_size(self.fitted_points)
        else:
            self.bounding_box_size = float(self.bounding_box_size)

        if self.is_tiny_fragment is None:
            self.is_tiny_fragment = (
                self.point_count < CURVE_TINY_MIN_POINT_COUNT
                or self.length < CURVE_TINY_MIN_LENGTH
                or self.bounding_box_size < CURVE_TINY_MIN_BOUNDING_BOX_SIZE
            )
        else:
            self.is_tiny_fragment = bool(self.is_tiny_fragment)

        self.source_section_result_id = (
            str(self.source_section_result_id)
            if self.source_section_result_id is not None
            else self.section_result_id
        )
        self.source_plane_id = (
            str(self.source_plane_id)
            if self.source_plane_id is not None
            else self.plane_id
        )
        self.metadata = dict(self.metadata)


@dataclass
class ProjectSurface:
    id: str
    name: str
    source_curve_ids: list[str]
    surface_type: str
    visible: bool
    metadata: dict[str, object]


@dataclass
class ProjectBrepSurface:
    id: str
    name: str
    source_curve_ids: list[str]
    brep_type: str
    backend: str
    visible: bool
    selected: bool = False
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ProjectLoftFeature:
    id: str
    name: str
    options: dict[str, object]
    brep_surface_id: str | None
    preview_surface_id: str | None
    last_build_success: bool
    last_build_reason: str
    last_build_warnings: list[str]
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class ProjectFourBoundaryPatchFeature:
    id: str
    name: str
    source_curve_ids: list[str]
    preserve_corners: bool
    match_directions: bool
    fill_method: str
    brep_surface_id: str | None
    preview_surface_id: str | None
    last_build_status: str
    metadata: dict[str, object] = field(default_factory=dict)


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
    brep_surfaces: list[ProjectBrepSurface] = field(default_factory=list)
    loft_features: list[ProjectLoftFeature] = field(default_factory=list)
    four_boundary_patch_features: list[ProjectFourBoundaryPatchFeature] = field(
        default_factory=list
    )
    # Unknown top-level fields are retained by the V3 repository boundary so
    # newer project producers can round-trip through older clients safely.
    metadata: dict[str, object] = field(default_factory=dict)


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


def _axis_origin(axis: str, offset: float) -> list[float]:
    origin = [0.0, 0.0, 0.0]
    origin[{"X": 0, "Y": 1, "Z": 2}.get(axis.upper(), 2)] = float(offset)
    return origin


def _axis_normal(axis: str) -> list[float]:
    normal = [0.0, 0.0, 0.0]
    normal[{"X": 0, "Y": 1, "Z": 2}.get(axis.upper(), 2)] = 1.0
    return normal


def _vector3_list(value: list[float] | tuple[float, float, float]) -> list[float]:
    values = list(value)
    if len(values) != 3:
        raise ValueError("Section plane orientation values must contain three numbers.")
    return [float(component) for component in values]


def _polyline_length(points: list[list[float]]) -> float:
    if len(points) < 2:
        return 0.0

    return float(sum(dist(start, end) for start, end in zip(points[:-1], points[1:])))


def _endpoint_distance(points: list[list[float]]) -> float:
    if len(points) < 2:
        return 0.0

    return float(dist(points[0], points[-1]))


def _bounding_box_size(points: list[list[float]]) -> float:
    if len(points) == 0:
        return 0.0

    columns = list(zip(*points, strict=False))
    return float(max(max(column) - min(column) for column in columns))
