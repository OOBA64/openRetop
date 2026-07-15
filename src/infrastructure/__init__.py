"""Replaceable external-system adapters for openRetop V3."""

from infrastructure.cad_adapter import CadCapabilities, PublicCadAdapter
from infrastructure.io_services import (
    DisplayProxyService,
    MeshImportService,
    ProgressEvent,
    ProjectFileService,
    StepExportService,
)
from infrastructure.persistence import (
    InMemoryProjectRepository,
    JsonProjectRepository,
    ProjectLoadResult,
    ProjectRepository,
    ProjectSaveResult,
)
from infrastructure.settings_repository import (
    InMemorySettingsRepository,
    JsonSettingsRepository,
    SettingsLoadResult,
    SettingsRepository,
    SettingsSaveResult,
)

__all__ = [
    "CadCapabilities",
    "DisplayProxyService",
    "InMemoryProjectRepository",
    "InMemorySettingsRepository",
    "JsonProjectRepository",
    "JsonSettingsRepository",
    "MeshImportService",
    "ProgressEvent",
    "ProjectFileService",
    "ProjectLoadResult",
    "ProjectRepository",
    "ProjectSaveResult",
    "PublicCadAdapter",
    "SettingsLoadResult",
    "SettingsRepository",
    "SettingsSaveResult",
    "StepExportService",
]
