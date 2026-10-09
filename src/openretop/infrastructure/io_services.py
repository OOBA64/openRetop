"""Import/export and project orchestration services with structured progress."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from openretop.infrastructure.persistence import (
    JsonProjectRepository,
    ProjectLoadResult,
    ProjectSaveResult,
)
from openretop.mesh.display_proxy import DisplayMeshResult, build_display_mesh
from openretop.mesh.loader import LoadedMesh, load_mesh
from openretop.project.project_data import ProjectData


@dataclass(frozen=True)
class ProgressEvent:
    operation: str
    stage: str
    message: str
    completed: int = 0
    total: int | None = None


ProgressListener = Callable[[ProgressEvent], None]


def _emit(listener: ProgressListener | None, event: ProgressEvent) -> None:
    if listener is not None:
        listener(event)


class MeshImportService:
    def import_mesh(
        self,
        path: str | Path,
        *,
        progress: ProgressListener | None = None,
    ) -> LoadedMesh:
        _emit(progress, ProgressEvent("mesh_import", "start", "Loading mesh"))
        loaded = load_mesh(path)
        _emit(
            progress,
            ProgressEvent(
                "mesh_import",
                "complete",
                f"Loaded {loaded.metadata.file_name}",
                completed=1,
                total=1,
            ),
        )
        return loaded


class DisplayProxyService:
    def build(
        self,
        source_mesh: object,
        *,
        quality: str,
        progress: ProgressListener | None = None,
    ) -> DisplayMeshResult:
        _emit(progress, ProgressEvent("display_proxy", "start", "Building display mesh"))
        result = build_display_mesh(source_mesh, quality=quality)
        _emit(progress, ProgressEvent("display_proxy", "complete", "Display mesh ready", 1, 1))
        return result


class ProjectFileService:
    """Coordinates repository calls without choosing a file-dialog policy."""

    def __init__(self, repository: JsonProjectRepository | None = None) -> None:
        self.repository = repository or JsonProjectRepository()

    def open_project(
        self,
        path: str | Path,
        *,
        progress: ProgressListener | None = None,
    ) -> ProjectLoadResult:
        _emit(progress, ProgressEvent("project_open", "start", "Opening project"))
        result = self.repository.read(path)
        _emit(
            progress,
            ProgressEvent(
                "project_open",
                "complete" if result.success else "error",
                "Project opened" if result.success else "Project could not be opened",
                1 if result.success else 0,
                1,
            ),
        )
        return result

    def save_project(
        self,
        project: ProjectData,
        path: str | Path,
        *,
        progress: ProgressListener | None = None,
    ) -> ProjectSaveResult:
        _emit(progress, ProgressEvent("project_save", "start", "Saving project"))
        result = self.repository.write(project, path)
        _emit(
            progress,
            ProgressEvent(
                "project_save",
                "complete" if result.success else "error",
                "Project saved" if result.success else "Project could not be saved",
                1 if result.success else 0,
                1,
            ),
        )
        return result
