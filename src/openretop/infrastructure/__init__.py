"""Replaceable external-system adapters for openRetop V3."""

from openretop.infrastructure.cad_adapter import CadCapabilities, PublicCadAdapter
from openretop.infrastructure.io_services import (
    DisplayProxyService,
    MeshImportService,
    ProgressEvent,
    ProjectFileService,
    StepExportService,
)
from openretop.infrastructure.persistence import (
    InMemoryProjectRepository,
    JsonProjectRepository,
    ProjectLoadResult,
    ProjectRepository,
    ProjectSaveResult,
)
from openretop.infrastructure.settings_repository import (
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
