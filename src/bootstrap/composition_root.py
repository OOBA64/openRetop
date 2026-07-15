"""Explicit V3 dependency composition without toolkit or global singletons."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.manual_curve_controller import ManualCurveController
from app.undo import UndoStack
from application.actions import ActionRegistry, create_core_action_registry
from application.analysis_controller import AnalysisController
from application.brep_controller import BrepController
from application.commands import CommandDispatcher
from application.curve_controller import CurveController
from application.dependencies import ApplicationDependencies
from application.events import EventPublisher
from application.region_controller import RegionController
from application.scene_controller import SceneController
from application.section_controller import SectionController
from application.selection import CallbackSelectionProvider
from application.selection_controller import SelectionController
from application.state import AppState
from application.surface_controller import SurfaceController
from application.transform_controller import TransformController
from application.visibility_controller import VisibilityController
from infrastructure.cad_adapter import PublicCadAdapter
from infrastructure.io_services import (
    DisplayProxyService,
    MeshImportService,
    ProjectFileService,
    StepExportService,
)
from infrastructure.persistence import JsonProjectRepository
from infrastructure.settings_repository import JsonSettingsRepository
from mesh.query_service import MeshQueryService
from settings.settings_data import AppSettings
from viewer.scene_builder import SceneBuilder


@dataclass(slots=True)
class ApplicationComposition:
    """All long-lived application services used by either desktop shell."""

    state: AppState
    events: EventPublisher
    undo: UndoStack
    dependencies: ApplicationDependencies
    actions: ActionRegistry
    commands: CommandDispatcher
    mesh_query_service: MeshQueryService
    cad: PublicCadAdapter
    project_repository: JsonProjectRepository
    settings_repository: JsonSettingsRepository
    project_files: ProjectFileService
    mesh_import: MeshImportService
    display_proxy: DisplayProxyService
    step_export: StepExportService
    scene_builder: SceneBuilder
    settings: AppSettings
    manual_curve_controller: ManualCurveController
    scene_controller: SceneController
    selection_controller: SelectionController
    visibility_controller: VisibilityController
    transform_controller: TransformController
    section_controller: SectionController
    curve_controller: CurveController
    region_controller: RegionController
    surface_controller: SurfaceController
    brep_controller: BrepController
    analysis_controller: AnalysisController


def create_application(
    *,
    settings_path: str | Path | None = None,
    project_repository: JsonProjectRepository | None = None,
    settings_repository: JsonSettingsRepository | None = None,
) -> ApplicationComposition:
    """Build one isolated application graph for a process or a test."""

    state = AppState()
    events = EventPublisher()
    undo = UndoStack()
    mesh_query = MeshQueryService()
    cad = PublicCadAdapter()
    settings_store = settings_repository or JsonSettingsRepository()
    settings = settings_store.load(settings_path)
    project_store = project_repository or JsonProjectRepository()
    selection_controller = SelectionController(state, events)
    dependencies = ApplicationDependencies(
        events=events,
        selection=CallbackSelectionProvider(selection_controller.snapshot),
        undo=undo,
    )
    actions = create_core_action_registry()
    commands = CommandDispatcher(dependencies)
    scene_controller = SceneController(state, events)
    visibility_controller = VisibilityController(state, events)
    transform_controller = TransformController(state, events)
    section_controller = SectionController(state, events)
    curve_controller = CurveController(
        state,
        events=events,
        mesh_query_service=mesh_query,
    )
    region_controller = RegionController(state, events=events)
    surface_controller = SurfaceController(
        state,
        events,
        mesh_query_service=mesh_query,
    )
    brep_controller = BrepController(state, events, cad_backend=cad)
    analysis_controller = AnalysisController(
        state,
        events=events,
        mesh_query_service=mesh_query,
    )
    manual_curve_controller = ManualCurveController(mesh_query_service=mesh_query)

    return ApplicationComposition(
        state=state,
        events=events,
        undo=undo,
        dependencies=dependencies,
        actions=actions,
        commands=commands,
        mesh_query_service=mesh_query,
        cad=cad,
        project_repository=project_store,
        settings_repository=settings_store,
        project_files=ProjectFileService(project_store),
        mesh_import=MeshImportService(),
        display_proxy=DisplayProxyService(),
        step_export=StepExportService(),
        scene_builder=SceneBuilder(),
        settings=settings,
        manual_curve_controller=manual_curve_controller,
        scene_controller=scene_controller,
        selection_controller=selection_controller,
        visibility_controller=visibility_controller,
        transform_controller=transform_controller,
        section_controller=section_controller,
        curve_controller=curve_controller,
        region_controller=region_controller,
        surface_controller=surface_controller,
        brep_controller=brep_controller,
        analysis_controller=analysis_controller,
    )
