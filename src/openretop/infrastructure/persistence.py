"""Typed project persistence boundaries and schema-compatible adapters."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

from openretop.project.atomic_io import write_text_atomic
from openretop.project.migrations import migrate_project_dict
from openretop.project.project_data import ProjectData
from openretop.project.project_io import project_from_dict, project_to_dict


@dataclass(frozen=True)
class PersistenceMessage:
    code: str
    message: str


@dataclass(frozen=True)
class ProjectLoadResult:
    project: ProjectData | None
    path: Path
    resolved_mesh_path: Path | None = None
    warnings: tuple[PersistenceMessage, ...] = ()
    errors: tuple[PersistenceMessage, ...] = ()
    migrated: bool = False

    @property
    def success(self) -> bool:
        return self.project is not None and not self.errors


@dataclass(frozen=True)
class ProjectSaveResult:
    path: Path
    warnings: tuple[PersistenceMessage, ...] = ()
    errors: tuple[PersistenceMessage, ...] = ()

    @property
    def success(self) -> bool:
        return not self.errors


class ProjectRepository(Protocol):
    """Port used by application services; dialogs never appear here."""

    def read(self, path: str | Path) -> ProjectLoadResult:
        ...

    def write(self, project: ProjectData, path: str | Path) -> ProjectSaveResult:
        ...


class JsonProjectRepository:
    """JSON adapter preserving the existing `.openretop` schema."""

    def read(self, path: str | Path) -> ProjectLoadResult:
        project_path = Path(path).expanduser()
        warnings: list[PersistenceMessage] = []
        try:
            raw = json.loads(project_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return ProjectLoadResult(
                None,
                project_path,
                errors=(PersistenceMessage("missing_project", f"Project does not exist: {project_path}"),),
            )
        except OSError as exc:
            return ProjectLoadResult(
                None,
                project_path,
                errors=(PersistenceMessage("project_read_failed", str(exc)),),
            )
        except json.JSONDecodeError as exc:
            return ProjectLoadResult(
                None,
                project_path,
                errors=(PersistenceMessage("invalid_project_json", f"Invalid project JSON: {exc.msg}"),),
            )

        if not isinstance(raw, dict):
            return ProjectLoadResult(
                None,
                project_path,
                errors=(PersistenceMessage("invalid_project_shape", "Project data must be a dictionary."),),
            )

        try:
            raw, applied = migrate_project_dict(raw)
        except ValueError as exc:
            return ProjectLoadResult(
                None,
                project_path,
                errors=(PersistenceMessage("unsupported_project_version", str(exc)),),
            )
        migrated = bool(applied)
        if applied and applied[0] == 0:
            warnings.append(
                PersistenceMessage("legacy_project_version", "Legacy project metadata was upgraded in memory.")
            )
        if migrated:
            warnings.append(
                PersistenceMessage(
                    "migrated_project",
                    "Project was written by an older version and was upgraded in memory "
                    f"(from v{applied[0]}); saving will write the current format.",
                )
            )
        if raw.get("units_assumed"):
            warnings.append(
                PersistenceMessage(
                    "units_assumed",
                    f"Project has no recorded length unit; assuming {raw.get('units', 'mm')}.",
                )
            )

        try:
            project = project_from_dict(raw)
        except (TypeError, ValueError, KeyError) as exc:
            return ProjectLoadResult(
                None,
                project_path,
                warnings=tuple(warnings),
                errors=(PersistenceMessage("invalid_project", str(exc)),),
                migrated=migrated,
            )

        resolved_mesh = self.resolve_mesh_path(project_path, project.mesh_path)
        if project.mesh_path and resolved_mesh is not None and not resolved_mesh.exists():
            warnings.append(
                PersistenceMessage("missing_mesh", f"Referenced mesh does not exist: {resolved_mesh}")
            )
        return ProjectLoadResult(
            project,
            project_path,
            resolved_mesh_path=resolved_mesh,
            warnings=tuple(warnings),
            migrated=migrated,
        )

    def write(self, project: ProjectData, path: str | Path) -> ProjectSaveResult:
        project_path = Path(path).expanduser()
        try:
            if not isinstance(project, ProjectData):
                raise TypeError("Expected ProjectData.")
            payload = project_to_dict(self.relativize_mesh_path(project, project_path))
            write_text_atomic(
                project_path,
                json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            )
        except (OSError, TypeError, ValueError) as exc:
            return ProjectSaveResult(
                project_path,
                errors=(PersistenceMessage("project_write_failed", str(exc)),),
            )
        return ProjectSaveResult(project_path)

    def load(self, path: str | Path) -> ProjectData:
        """Compatibility convenience that raises on a failed read."""

        result = self.read(path)
        if not result.success or result.project is None:
            message = result.errors[0].message if result.errors else "Project could not be loaded."
            raise ValueError(message)
        return result.project

    def save(self, project: ProjectData, path: str | Path) -> None:
        result = self.write(project, path)
        if not result.success:
            message = result.errors[0].message if result.errors else "Project could not be saved."
            raise OSError(message)

    @staticmethod
    def relativize_mesh_path(project: ProjectData, project_path: str | Path) -> ProjectData:
        """Return a copy whose mesh path is stored relative to the project file.

        Keeps projects portable when the project and mesh move together. Falls
        back to the absolute path when no relative form exists (other drive).
        """

        if not project.mesh_path:
            return project
        mesh = Path(project.mesh_path).expanduser()
        if not mesh.is_absolute():
            mesh = Path(project_path).expanduser().parent / mesh
        base = Path(project_path).expanduser().resolve(strict=False).parent
        try:
            relative = os.path.relpath(mesh.resolve(strict=False), base)
        except ValueError:
            return replace(project, mesh_path=str(mesh.resolve(strict=False)))
        return replace(project, mesh_path=Path(relative).as_posix())

    @staticmethod
    def resolve_mesh_path(project_path: str | Path, mesh_path: str | None) -> Path | None:
        if not mesh_path:
            return None
        candidate = Path(mesh_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path(project_path).expanduser().parent / candidate
        return candidate.resolve(strict=False)


class InMemoryProjectRepository:
    """Small deterministic fake for bootstrap and application tests."""

    def __init__(self, projects: dict[str, ProjectData] | None = None) -> None:
        self.projects = dict(projects or {})

    def read(self, path: str | Path) -> ProjectLoadResult:
        key = str(Path(path))
        project = self.projects.get(key)
        if project is None:
            return ProjectLoadResult(
                None,
                Path(path),
                errors=(PersistenceMessage("missing_project", f"Project does not exist: {path}"),),
            )
        return ProjectLoadResult(project, Path(path))

    def write(self, project: ProjectData, path: str | Path) -> ProjectSaveResult:
        key = str(Path(path))
        self.projects[key] = project
        return ProjectSaveResult(Path(path))
