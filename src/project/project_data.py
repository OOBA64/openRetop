"""Project data models for openRetop project files."""

from __future__ import annotations

from dataclasses import dataclass


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
class ProjectData:
    version: int
    name: str
    mesh_path: str | None
    transform: ProjectTransform
    display: ProjectDisplaySettings
    section: ProjectSectionSettings


def default_project_data() -> ProjectData:
    return ProjectData(
        version=PROJECT_VERSION,
        name="Untitled Project",
        mesh_path=None,
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
