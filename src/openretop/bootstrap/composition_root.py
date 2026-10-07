"""Explicit V3 dependency composition without toolkit or global singletons."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openretop.application.actions import ActionRegistry, create_core_action_registry
from openretop.application.analysis_controller import AnalysisController
from openretop.application.brep_controller import BrepController
from openretop.application.commands import CommandDispatcher
from openretop.application.curve_controller import CurveController
from openretop.application.dependencies import ApplicationDependencies
from openretop.application.events import EventPublisher
from openretop.application.manual_curve_controller import ManualCurveController
from openretop.application.region_controller import RegionController
from openretop.application.scene_controller import SceneController
from openretop.application.section_controller import SectionController
from openretop.application.selection import CallbackSelectionProvider
from openretop.application.selection_controller import SelectionController
from openretop.application.state import AppState
from openretop.application.surface_controller import SurfaceController
from openretop.application.transform_controller import TransformController
from openretop.application.undo import UndoStack
from openretop.application.visibility_controller import VisibilityController
from openretop.application.workflow_service import WorkflowService
from openretop.infrastructure.cad_adapter import PublicCadAdapter
from openretop.infrastructure.io_services import (
    DisplayProxyService,
    MeshImportService,
    ProjectFileService,
    StepExportService,
)
from openretop.infrastructure.persistence import JsonProjectRepository, ProjectRepository
from openretop.infrastructure.settings_repository import JsonSettingsRepository, SettingsRepository
from openretop.mesh.query_service import MeshQueryService
from openretop.settings.settings_data import AppSettings
from openretop.viewer.scene_builder import SceneBuilder


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
    project_repository: ProjectRepository
    settings_repository: SettingsRepository
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
    workflow: WorkflowService


def create_application(
    *,
    settings_path: str | Path | None = None,
    project_repository: ProjectRepository | None = None,
    settings_repository: SettingsRepository | None = None,
    cad_adapter: PublicCadAdapter | None = None,
) -> ApplicationComposition:
    """Build one isolated application graph for a process or a test."""

    state = AppState()
    events = EventPublisher()
    undo = UndoStack()
    mesh_query = MeshQueryService()
    cad = cad_adapter or PublicCadAdapter()
    settings_store = settings_repository or JsonSettingsRepository()
    settings = settings_store.read(settings_path).settings
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

    workflow = WorkflowService(
        state=state,
        settings=settings,
        undo=undo,
        scene=scene_controller,
        selection=selection_controller,
        visibility=visibility_controller,
        transform=transform_controller,
        section=section_controller,
        curve=curve_controller,
        manual_curve=manual_curve_controller,
        region=region_controller,
        surface=surface_controller,
        brep=brep_controller,
        analysis=analysis_controller,
    )
    for action in actions.definitions:
        commands.register(
            action.command_id,
            lambda command, _dependencies, action_id=action.id: workflow.dispatch(
                action_id,
                command.payload,
            ),
        )

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
        workflow=workflow,
    )
