"""Supported openRetop V3 PySide6 workbench."""

from __future__ import annotations

import copy
import logging
import sys
import threading
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Mapping

import numpy as np
from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFrame,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from openretop.application.actions import ActionContext, create_core_action_registry
from openretop.application.commands import CommandRequest
from openretop.application.guidance import build_guidance
from openretop.application.keybindings import shortcut_conflicts, shortcut_overrides
from openretop.application.results import CommandResult
from openretop.application.scene_ids import (
    NODE_MESH,
    NODE_REGIONS,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    region_node_id,
    section_plane_id_from_node,
    section_plane_node_id,
    section_result_id_from_node,
    section_result_node_id,
)
from openretop.application.state import AppState, MeshObjectState
from openretop.application.workflow_service import PRESENTATION_ACTION_IDS
from openretop.bootstrap import ApplicationComposition, create_application
from openretop.geometry.units import UNIT_CODES, get_unit
from openretop.infrastructure.io_services import ProgressEvent
from openretop.mesh.display_proxy import normalize_proxy_quality
from openretop.modeling.persistence import PROJECT_KEY as MODEL_PROJECT_KEY
from openretop.modeling.persistence import model_from_dict, model_to_dict
from openretop.presentation.qt.adaptive_grid import format_spacing
from openretop.presentation.qt.background import InlineExecutor, TaskExecutor, ThreadedExecutor
from openretop.presentation.qt.next_steps import NextStepsPanel
from openretop.presentation.qt.preferences_dialog import CommandShortcut, PreferencesDialog
from openretop.presentation.qt.surfacing_workbench import SURFACING_HEAVY_ACTIONS, SurfacingWorkbenchMixin
from openretop.presentation.qt.transform_overlays import transformed_object_origin
from openretop.presentation.qt.viewport import QtSceneViewport
from openretop.project.project_session import restore_project_state
from openretop.project.project_state import project_from_app_state
from openretop.sections.section_state import get_active_plane, plane_origin
from openretop.settings.settings_data import DISPLAY_COLOR_FIELDS
from openretop.viewer.modeling_scene import model_id_from_node, model_node_id
from openretop.viewer.picking_service import MeshPickResult, SceneObjectPickResult
from openretop.viewer.scene_builder import SceneBuildOptions
from openretop.viewer.scene_synchronizer import ActorUpdateDiagnostics
from openretop.viewer.scene_types import CameraRequest, ToolPreviewState
from workbench_ui import (
    ActionDefinition,
    ActionRegistry,
    ApplicationShell,
    CommandPaletteDialog,
    CommandPaletteWidget,
    FieldDefinition,
    MenuItem,
    MenuSchema,
    PanelDescriptor,
    PropertyInspectorModel,
    PropertyInspectorWidget,
    SceneNode,
    SceneTreeModel,
    SceneTreeWidget,
    ToolbarItem,
    ToolbarSchema,
)
from workbench_ui.contracts import WorkspaceDescriptor
from workbench_ui.icons import themed_icon
from workbench_ui.shell import action_tooltip

_LOG = logging.getLogger(__name__)

# the stages of the work, each with its own tools (the toolbar row under the tabs)
WORKSPACES = (
    WorkspaceDescriptor("scan", "Scan", "Prepare the scan: align it, cut sections, select regions, measure."),
    WorkspaceDescriptor("surface", "Surface", "Curves on the scan and surfaces fitted to it: organic shapes."),
    WorkspaceDescriptor("solid", "Solid", "Sketches on planes through the scan, extruded into solids."),
)
DEFAULT_WORKSPACE = "surface"


# Commands that build geometry (sections, surfaces, solids) and can take seconds.
# With a threaded executor they run off the UI thread while the window is locked.
HEAVY_ACTIONS = frozenset({"section.compute", *SURFACING_HEAVY_ACTIONS})


# Scene tree row icons, by node kind.
_TREE_KIND_ICONS = {
    "root": "project",
    "mesh": "mesh",
    "group": "folder",
    "section_plane": "section_plane",
    "section_result": "section_cut",
    "curve": "curve",
    "region": "region",
    "feature": "feature",
    "model_surface": "surface",
    "model_body": "solid",
}

PROPERTIES_MIN_WIDTH = 280  # px: fits the Next-steps buttons and the X/Y/Z boxes without clipping

# Starting any of these ends the measure tool, which would otherwise compete for the clicks.
_TOOL_START_ACTIONS = frozenset(
    {"region.start", "transform.move", "transform.rotate"}
)

# Commands that engage the Section tool, which is what makes the section planes visible.
_SECTION_TOOL_ACTIONS = frozenset(
    {
        "section.add_plane",
        "section.compute",
        "section.delete_plane",
        "section.set_axis",
        "section.set_offset",
        "section.toggle_plane_visibility",
    }
)


_IMPORT_ERRORS = (OSError, RuntimeError, ValueError)
MESH_SUFFIXES = frozenset({".stl", ".obj", ".ply"})
PROJECT_SUFFIX = ".openretop"


@dataclass(frozen=True)
class _ModelRead:
    """A mesh read and display-proxied on a worker thread, not yet installed."""

    loaded: object
    proxy: object


_FILE_ACTIONS = (
    ("file.new_project", "New Project", "File", "Ctrl+N", "Start an empty project."),
    ("file.open_model", "Open Model", "File", "Ctrl+O", "Import an STL, OBJ or PLY scan and choose its length unit."),
    ("file.open_project", "Open Project", "File", "Ctrl+Shift+O", "Open an .openretop project and reload its scan."),
    ("file.save_project", "Save Project", "File", "Ctrl+S", "Save the project (the scan itself is referenced, not copied)."),
    ("file.save_project_as", "Save Project As", "File", "Ctrl+Shift+S", "Save the project under a new name."),
    ("file.export_model", "Export Model...", "File", "Ctrl+E", "Write the model's surfaces and bodies (selected, or all visible) to STEP or IGES."),
    ("view.command_palette", "Command Palette...", "View", "Ctrl+K", "Search every command by name; unavailable ones show what they need."),
    ("file.set_units", "Set Model Units...", "Edit", None, "Change the length unit the model coordinates are labelled with (does not rescale)."),
    ("file.preferences", "Preferences", "Edit", "Ctrl+,", "Display, import and keyboard settings."),
    ("file.quit", "Quit", "File", "Alt+F4", "Close openRetop."),
    ("help.about", "About openRetop V3", "Help", None, "Version and credits."),
)


class OpenRetopV3Window(SurfacingWorkbenchMixin, ApplicationShell):
    """Qt shell backed only by V3 controllers, services, and scene snapshots."""

    def __init__(
        self,
        composition: ApplicationComposition | None = None,
        *,
        parent: QWidget | None = None,
        executor: TaskExecutor | None = None,
    ) -> None:
        self.composition = composition or create_application()
        self._executor: TaskExecutor = executor or InlineExecutor()
        busy_changed = getattr(self._executor, "busy_changed", None)
        if busy_changed is not None:
            busy_changed.connect(lambda _busy: self._sync_action_state())
        self._application_actions = create_core_action_registry()
        self._framework_actions = self._make_framework_actions()
        super().__init__(
            action_registry=self._framework_actions,
            menu_schemas=self._menu_schemas(),
            toolbar_schemas=self._toolbar_schemas(),
            workspaces=self._workspaces(),
            parent=parent,
        )
        self.resize(
            self.composition.settings.ui.window_width,
            self.composition.settings.ui.window_height,
        )
        remembered = str(self.composition.settings.future.get("workspace", DEFAULT_WORKSPACE))
        self.set_active_workspace(remembered if remembered in {item.id for item in WORKSPACES} else DEFAULT_WORKSPACE)
        self.workspace_changed.connect(self._remember_workspace)
        self._camera_request = CameraRequest.frame_all()
        self._section_tool = False  # the Section tool is engaged: section planes are shown
        self.current_project_path: Path | None = None
        self.project_dirty = False
        self._scene_model = SceneTreeModel()
        self._progress_dialog: QProgressDialog | None = None
        self._last_project_warnings: tuple[str, ...] = ()

        self.scene_tree = SceneTreeWidget(self._scene_model, self)
        tree_icon_color = self.theme_manager.color("text_muted")
        self.scene_tree.set_kind_icons(
            {
                kind: themed_icon(icon, tree_icon_color, self.theme_manager.color("text_faint"), size=16)
                for kind, icon in _TREE_KIND_ICONS.items()
            }
        )
        self.scene_tree.selection_changed.connect(self._on_tree_selection)
        self.scene_tree.visibility_changed.connect(
            self._on_tree_visibility,
            Qt.ConnectionType.QueuedConnection,
        )
        self.scene_tree.renamed.connect(self._on_tree_rename)
        self.scene_tree.context_action_requested.connect(self._on_tree_context_action)
        self.viewport = QtSceneViewport(self)
        self.viewport.pointer_event.connect(self._on_viewport_pointer)
        self.viewport.view_controls.action_requested.connect(
            self._dispatch_framework_action
        )
        self.viewport.initialization_failed.connect(self._on_viewport_failure)
        self.viewport.render_failed.connect(self._on_viewport_failure)
        self.viewport.scene_synchronized.connect(self._on_scene_synchronized)
        self.viewport.grid_spacing_changed.connect(lambda _spacing: self.set_info_message(self._model_info_text()))
        self.viewport.ready.connect(self._on_viewport_ready)
        if self.viewport.interactor is not None:
            self.viewport.interactor.installEventFilter(self)
        self.inspector = PropertyInspectorWidget(PropertyInspectorModel(), self)
        self.inspector.value_changed.connect(self._on_inspector_value)
        self.inspector.validation_failed.connect(self._on_inspector_validation_failed)
        self.palette = CommandPaletteWidget(self._framework_actions, self)
        self.palette.action_triggered.connect(self._dispatch_framework_action)
        self._palette_dialog = CommandPaletteDialog(self._framework_actions, self)
        self._palette_dialog.action_triggered.connect(self._run_palette_action)
        # The active tool's instructions float at the bottom of the viewport (not a second
        # copy in the status bar, which already shows the latest message).
        self.tool_modes.subscribe(self._on_tool_mode_changed)
        self._diagnostics = QLabel("", self)
        self._diagnostics.setWordWrap(True)
        self.add_panel(PanelDescriptor("scene", "Scene", area="left"), self.scene_tree)
        self.next_steps = NextStepsPanel(self)
        self.next_steps.action_requested.connect(lambda action_id: self._framework_actions.invoke(action_id))
        self.next_steps.recent_requested.connect(lambda value: self.open_project_path(Path(value)))
        properties = QWidget(self)
        properties_layout = QVBoxLayout(properties)
        properties_layout.setContentsMargins(0, 0, 0, 0)
        properties_layout.addWidget(self.next_steps)
        properties_layout.addWidget(self.inspector)
        self._init_surfacing(properties_layout)
        # Scrolls instead of growing: a tall panel must never stretch the main window.
        properties_scroll = QScrollArea(self)
        properties_scroll.setObjectName("properties_scroll")
        properties_scroll.setWidgetResizable(True)
        properties_scroll.setFrameShape(QFrame.Shape.NoFrame)
        properties_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        properties_scroll.setWidget(properties)
        # a scroll area reports almost no minimum width, which collapsed the dock to a sliver
        properties_scroll.setMinimumWidth(PROPERTIES_MIN_WIDTH)
        self.add_panel(PanelDescriptor("properties", "Properties", area="right"), properties_scroll)
        self.setAcceptDrops(True)
        self.add_panel(PanelDescriptor("commands", "Command Palette", area="bottom", visible=False), self.palette)
        diagnostics = QWidget(self)
        diagnostics_layout = QVBoxLayout(diagnostics)
        diagnostics_layout.addWidget(self._diagnostics)
        self.add_panel(PanelDescriptor("diagnostics", "Diagnostics", area="bottom", visible=False), diagnostics)
        self.set_workspace(self.viewport)
        self._update_window_title()
        # This refresh builds UI models and submits the initial snapshot.  The
        # viewport retains it until VTKViewportWidget emits ready after show().
        self.refresh()

    def _make_framework_actions(self) -> ActionRegistry:
        registry = ActionRegistry()
        shortcut_overrides = self._shortcut_overrides()
        for definition in self._application_actions.definitions:
            registry.register(
                ActionDefinition(
                    id=definition.id,
                    label=definition.label,
                    category=_menu_category(definition.id, definition.category),
                    description=definition.description,
                    shortcut=shortcut_overrides.get(definition.id, definition.shortcut),
                    checkable=definition.checkable,
                    dispatch=lambda payload, action_id=definition.id: self._dispatch_application_action(action_id, payload),
                    metadata={"command_id": definition.command_id, **dict(definition.metadata)},
                )
            )
        for action_id, label, category, shortcut, description in _FILE_ACTIONS:
            registry.register(
                ActionDefinition(
                    action_id,
                    label,
                    category=category,
                    description=description,
                    shortcut=shortcut_overrides.get(action_id, shortcut),
                    dispatch=lambda payload, action_id=action_id: self._dispatch_framework_action(action_id, payload),
                )
            )
        for index, path in enumerate(self._recent_projects(), start=1):
            registry.register(
                ActionDefinition(
                    f"file.recent.{index}",
                    f"Open Recent: {Path(path).name}",
                    category="File",
                    dispatch=lambda _payload, value=path: self.open_project_path(Path(value)),
                    metadata={"path": path},
                )
            )
        return registry

    def _shortcut_overrides(self) -> dict[str, str]:
        return shortcut_overrides(self.composition.settings.keybinds, self.composition.settings.future)

    def _menu_schemas(self) -> tuple[MenuSchema, ...]:
        result: list[MenuSchema] = []
        for category in ("File", "Edit", "View", "Create", "Modify", "Inspect", "Help"):
            ids = [item.id for item in self._framework_actions.definitions if item.category == category]
            result.append(MenuSchema(category, tuple(MenuItem(action_id=value) for value in ids)))
        return tuple(result)

    @staticmethod
    def _workspaces() -> tuple[WorkspaceDescriptor, ...]:
        return WORKSPACES

    @staticmethod
    def _toolbar_schemas() -> tuple[ToolbarSchema, ...]:
        # (action, icon, short label, starts a new group). Common to every workspace: file |
        # history | view. Then one toolbar per workspace, in the order a part is worked on.
        common = (
            ("file.open_model", "open_scan", "Open Scan", False),
            ("file.open_project", "open_project", "Open Project", False),
            ("file.save_project", "save", "Save", False),
            ("edit.undo", "undo", "Undo", True),
            ("edit.redo", "redo", "Redo", False),
            ("view.frame_all", "frame_all", "Frame All", True),
            ("view.frame_selected", "frame_selected", "Frame Selected", False),
        )
        scan = (  # preparing the scan: align it, cut it, look at it
            ("transform.move", "move", "Move", False),
            ("transform.rotate", "rotate", "Rotate", False),
            ("section.add_plane", "section_plane", "Section Plane", True),
            ("section.compute", "section_cut", "Cut Section", False),
            ("region.start", "region", "Region", True),
            ("measure.distance", "measure", "Measure", False),
        )
        surface = (  # ExModel-style surfacing on organic shapes
            ("model.sketch", "curve", "Surface Sketch", False),
            ("model.fit_surface", "fit_surface", "Fit Surface", False),
            ("model.loft", "loft", "Loft", True),
            ("model.fill", "fill", "Fill", False),
            ("model.extend", "extend", "Extend", False),
            ("model.trim", "trim", "Trim", True),
            ("model.compare", "compare", "Compare", True),
            ("file.export_model", "save", "Export", False),
        )
        solid = (  # sketches on planes made into solids
            ("model.plane_sketch", "sketch_3d", "3D Sketch", False),
            ("model.section_sketch", "section_sketch", "Section Sketch", False),
            ("model.section_edit", "section_sketch", "Edit Sketch", False),
            ("model.extrude", "extrude", "Extrude", False),
            ("model.compare", "compare", "Compare", True),
            ("file.export_model", "save", "Export", False),
        )

        def items(rows):
            return tuple(ToolbarItem(action_id, icon=icon, label=label, separator_before=group) for action_id, icon, label, group in rows)

        return (
            ToolbarSchema("Main", items(common)),
            ToolbarSchema("Scan", items(scan), workspace="scan"),
            ToolbarSchema("Surface Modeling", items(surface), workspace="surface"),
            ToolbarSchema("Solid Modeling", items(solid), workspace="solid"),
        )

    def _dispatch_framework_action(
        self,
        action_id: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
        if action_id.startswith("file.") and action_id != "file.quit" and self._reject_while_busy():
            return False
        if action_id == "file.new_project":
            return self.new_project()
        if action_id == "file.open_model":
            return self.open_model()
        if action_id == "file.open_project":
            return self.open_project()
        if action_id == "file.save_project":
            return self.save_project()
        if action_id == "file.save_project_as":
            return self.save_project(as_dialog=True)
        if action_id == "file.export_model":
            return self.export_model()
        if action_id == "view.command_palette":
            return self.show_command_palette()
        if action_id == "file.set_units":
            return self.set_model_units()
        if action_id == "file.preferences":
            return self.show_preferences()
        if action_id == "file.quit":
            return self.close()
        if action_id == "help.about":
            QMessageBox.information(
                self,
                "About openRetop V3",
                "openRetop V3\nPySide6 workbench with incremental VTK scene rendering.",
            )
            return True
        if action_id.startswith("file.recent."):
            definition = self._framework_actions.require(action_id)
            path = definition.metadata.get("path")
            return False if path is None else self.open_project_path(Path(str(path)))
        return self._dispatch_application_action(action_id, payload)

    def _dispatch_application_action(
        self,
        action_id: str,
        payload: Mapping[str, object] | None = None,
    ) -> bool:
        if action_id in PRESENTATION_ACTION_IDS or action_id.startswith("view.named."):
            return self._dispatch_view_action(action_id)
        if self._reject_while_busy():
            return False
        if action_id == "measure.distance":
            busy_tool = self._other_tool_active()
            if busy_tool:
                self.set_status_message(f"Finish the {busy_tool} first (Enter or Esc), then measure.")
                return False
        elif action_id in _TOOL_START_ACTIONS and self.composition.measure_controller.active:
            self.composition.measure_controller.finish()
            if self.tool_modes.state.id == "measure":
                self.tool_modes.cancel()
        if action_id in _SECTION_TOOL_ACTIONS:
            self._enter_section_tool()
        if action_id in {"transform.move", "transform.rotate"}:
            plane = self._section_tool_plane()
            if plane is not None and self.composition.state.selected_item not in {"model", "section_plane"}:
                # The Section tool promises "G moves and R rotates the plane": act on its
                # active plane even when nothing is selected (R used to fall through to VTK,
                # which reset the camera).
                self.composition.selection_controller.select_nodes((section_plane_node_id(plane.id),))
        if action_id in {"transform.move", "transform.rotate"} and not (payload and "mouse_start" in payload):
            # Start from where the pointer is now (as the original app did), not from (0, 0).
            payload = {**(payload or {}), "mouse_start": self.viewport.last_pointer_position}
        if action_id in HEAVY_ACTIONS and self._executor.asynchronous:
            return self._run_background(
                self._heavy_label(action_id),
                lambda: self._command_result(action_id, payload),
                lambda result: self._consume_result(action_id, result),
            )
        if action_id == "scene.rename_selected" and not payload:
            selection = self.composition.selection_controller.snapshot()
            if len(selection.ids) + len(self.composition.state.model.selected_ids) != 1:
                self.set_status_message("Select one object to rename.")
                return False
            name, accepted = QInputDialog.getText(self, "Rename", "Name")
            if not accepted:
                return False
            payload = {"name": name}
        result = self._command_result(action_id, payload)
        self._consume_result(action_id, result)
        if action_id == "view.proxy_quality" and result.success:
            self._rebuild_display_proxy()
        return result.success

    def _dispatch_view_action(self, action_id: str) -> bool:
        if action_id == "view.frame_all" or action_id == "view.reset":
            self._camera_request = CameraRequest.frame_all()
        elif action_id == "view.frame_selected" or action_id == "view.frame_region":
            ids = tuple(self.composition.selection_controller.snapshot().ids) + self._surfacing_selected_nodes()
            self._camera_request = CameraRequest.frame_selected(ids)
        elif action_id.startswith("view.named."):
            self._camera_request = CameraRequest.named_view(action_id.rsplit(".", 1)[-1])
        elif action_id == "view.roll_left":
            self._camera_request = CameraRequest.roll(-15.0)
        elif action_id == "view.roll_right":
            self._camera_request = CameraRequest.roll(15.0)
        else:
            return False
        self.refresh()
        return True

    def _command_result(
        self,
        action_id: str,
        payload: Mapping[str, object] | None = None,
    ) -> CommandResult:
        if self._executor.busy and threading.current_thread() is threading.main_thread():
            return CommandResult.failure(f"Busy: {self._executor.label}", status=f"Busy: {self._executor.label}")
        definition = self._application_actions.require(action_id)
        return self.composition.commands.dispatch(
            CommandRequest(
                command_id=definition.command_id,
                action_id=action_id,
                payload=payload or {},
            )
        )

    def _consume_result(self, action_id: str, result: CommandResult) -> None:
        message = result.status or (result.errors[0] if result.errors else "Command completed")
        self.set_status_message(message)
        if result.warnings:
            self._diagnostics.setText("\n".join(result.warnings))
        if result.dirty:
            self.set_project_dirty(True)
        self._sync_tool_mode(action_id, result)
        if (
            action_id.startswith("transform.constrain_")
            and result.success
            and self.composition.transform_controller.active
        ):
            # Changing the lock mid-grab moves the object at once, not on the next mouse move.
            relocked = self._update_transform(self.viewport.last_pointer_position)
            if relocked.status:
                self.set_status_message(relocked.status)
        if action_id == "transform.pointer":
            # Only the 3D scene and the live transform values: the rest of the panels catch up
            # when the transform is confirmed or cancelled (rebuilding them made drags stutter).
            self._render_scene()
            self._show_live_transform_values()
        else:
            self.refresh()

    def _sync_tool_mode(self, action_id: str, result: CommandResult) -> None:
        if not result.success:
            return
        self._surfacing_tool_mode(action_id, result)
        if action_id == "region.start":
            self._section_tool = False
            self.tool_modes.enter("region", "Click the mesh to grow a region; Esc finishes.")
        elif action_id == "measure.distance":
            self.tool_modes.enter("measure", "Click two points on the scan to measure. Esc cancels a point, then finishes.")
        elif action_id == "measure.finish" and self.tool_modes.state.id == "measure":
            self.tool_modes.finish()
        elif action_id in {"transform.move", "transform.rotate"}:
            self.tool_modes.enter(
                "transform",
                "Move the pointer or type a value. X/Y/Z lock an axis, Shift+X/Y/Z a plane. "
                "Enter confirms, Esc cancels.",
            )
            if self.viewport.interactor is not None:
                # keys belong to the grab now (locks, typed values), not to the tree or a field
                self.viewport.interactor.setFocus()
        elif action_id in {"region.finish", "transform.confirm"}:
            self.tool_modes.finish()
        elif action_id == "transform.cancel":
            self.tool_modes.cancel()

    def _on_tree_selection(self, selection: object) -> None:
        ids = self._surfacing_tree_selection(tuple(getattr(selection, "ids", ())))
        self._section_tool = any(
            value == NODE_SECTION_PLANES or section_plane_id_from_node(value) is not None for value in ids
        )
        result = self.composition.selection_controller.select_nodes(ids)
        self.set_status_message(result.status or "Selection changed")
        self.refresh()

    def _on_tree_visibility(self, node_id: str, visible: bool) -> None:
        if self._surfacing_tree_visibility(node_id, visible):
            return
        # Checkbox state is an explicit command target, not an implicit
        # selection change.  WorkflowService records at most one undo payload.
        result = self._command_result(
            "scene.set_visibility",
            {"node_ids": (node_id,), "visible": bool(visible)},
        )
        self._consume_result("tree.visibility", result)

    def _on_tree_rename(self, node_id: str, name: str) -> None:
        if self._surfacing_tree_rename(node_id, name):
            return
        self.composition.selection_controller.select_nodes((node_id,))
        result = self._command_result("scene.rename_selected", {"name": name})
        self._consume_result("scene.rename_selected", replace_dirty(result))

    def _on_tree_context_action(self, action_id: str, context: object) -> None:
        ids = self._surfacing_tree_selection(tuple(getattr(context, "ids", ())))
        if ids:
            self.composition.selection_controller.select_nodes(ids)
        self._dispatch_framework_action(action_id)

    def _show_live_transform_values(self) -> None:
        state = self.composition.state
        values: dict[str, object] = {}
        if state.mesh_object is not None:
            values["location"] = tuple(float(value) for value in state.mesh_object.location)
            values["rotation"] = tuple(float(value) for value in state.mesh_object.rotation)
        session = state.transform_state
        if session is not None and session.section_plane_id is not None:
            plane = next((item for item in state.section_collection.planes if item.id == session.section_plane_id), None)
            if plane is not None:
                values["section_offset"] = float(plane.offset)
        self.inspector.show_values(values)

    def _update_transform(self, widget_position: tuple[int, int]) -> CommandResult:
        return self.composition.transform_controller.update(
            widget_position,
            camera=self.viewport.camera_vectors(),
            model_bounds=None,  # the model's own bounds: scene bounds grow as it moves, which accelerated the drag
            fine=bool(
                self.viewport.interactor is not None
                and self.viewport.interactor.GetShiftKey()
            ),
        )

    def _on_viewport_pointer(
        self,
        event_name: str,
        x_position: int,
        y_position: int,
        pick: object,
    ) -> None:
        if self.composition.transform_controller.active:
            if event_name == "motion":
                self._consume_result(
                    "transform.pointer",
                    self._update_transform(self.viewport.to_widget_position(x_position, y_position)),
                )
            return

        if self._surfacing_pointer(event_name, x_position, y_position, pick):
            return

        region = self.composition.region_controller
        if region.session.active:
            gesture = region.handle_pointer_event(event_name, x_position, y_position)
            if event_name == "left_release" and bool(gesture.metadata.get("is_click")):
                if not isinstance(pick, MeshPickResult):
                    pick = self.viewport.pick_mesh(x_position, y_position)
                mesh_pick = pick if isinstance(pick, MeshPickResult) else MeshPickResult(False)
                result = region.select_seed(
                    mesh_pick.triangle_index if mesh_pick.hit else None,
                    mesh=None
                    if self.composition.state.mesh_object is None
                    else self.composition.state.mesh_object.display_mesh,
                )
                self._consume_result("region.pointer", result)
            elif gesture.changed:
                self.refresh()
            return

        measure = self.composition.measure_controller
        if measure.active:
            # Measuring: a click places a point on the scan; drags still orbit, and picks never
            # change the selection.
            if event_name == "left_release" and self.viewport.last_pointer_release_was_click:
                if not isinstance(pick, MeshPickResult):
                    pick = self.viewport.pick_mesh(x_position, y_position)
                point = pick.position if isinstance(pick, MeshPickResult) and pick.hit else None
                self._consume_result("measure.pointer", measure.add_point(point))
            return

        if event_name != "left_release" or not self.viewport.last_pointer_release_was_click:
            return
        if not isinstance(pick, SceneObjectPickResult):
            pick = self.viewport.pick_scene_object(x_position, y_position)
        picked_node = (_node_id_for_pick(pick) or "") if isinstance(pick, SceneObjectPickResult) and pick.hit else ""
        if picked_node.startswith("sketch:"):
            self.composition.selection_controller.select_nodes(())
            self.composition.modeling_controller.select_entities(())
            result = self.composition.modeling_controller.sketch_select_curves((picked_node.split(":", 1)[1],))
            self.set_status_message(result.status)
            self.refresh()
            return
        picked_model = model_id_from_node(picked_node) if picked_node else None
        if picked_model is not None:
            self.composition.selection_controller.select_nodes(())
            result = self.composition.modeling_controller.select_entities((picked_model,))
            self.set_status_message(result.status)
            self.refresh()
            return
        if isinstance(pick, SceneObjectPickResult) and pick.hit:
            node_id = _node_id_for_pick(pick)
            if node_id is not None:
                self._section_tool = section_plane_id_from_node(node_id) is not None
                # a click selects only what it hit: model items and sketch curves let go too
                self.composition.modeling_controller.select_entities(())
                self.composition.modeling_controller.sketch_select_curves(())
                result = self.composition.selection_controller.select_nodes((node_id,))
                self.set_status_message(result.status or "Selection changed")
                self.refresh()
        elif (
            self._leave_section_tool()
            or self.composition.selection_controller.snapshot().ids
            or self.composition.state.model.selected_ids
            or self.composition.state.model.selected_curve_ids
        ):
            # A plain click on empty space deselects, as in every other CAD viewport.
            self.composition.selection_controller.select_nodes(())
            self.composition.modeling_controller.select_entities(())
            self.composition.modeling_controller.sketch_select_curves(())
            self.set_status_message("Selection cleared")
            self.refresh()

    def keyPressEvent(self, event: object) -> None:
        from PySide6.QtWidgets import QAbstractSpinBox, QComboBox, QLineEdit, QTextEdit

        if self._field_enter and event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self._field_enter = False
            event.accept()
            return
        if isinstance(QApplication.focusWidget(), (QAbstractSpinBox, QLineEdit, QTextEdit, QComboBox)):
            # A key a text or number field passed on (Qt hands Enter up so dialogs can take
            # it): it was typed into the field, not meant for the tool (Enter after a
            # dimension value finished the whole 3D Sketch).
            super().keyPressEvent(event)
            return
        if self._handle_tool_key(event.key(), event.text()):
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: object, event: object) -> bool:
        if watched is self.viewport.interactor:
            if event.type() == QEvent.ShortcutOverride and (
                self._is_typed_value_key(event.key(), event.text()) or self._surfacing_claims_key(event.key(), event.modifiers())
            ):
                # While grabbing, digits type a value: claim them before shortcuts such as
                # "0" (Isometric) can fire. In the 3D Sketch, L R C A S pick its drawing tools.
                event.accept()
                return True
            if event.type() == QEvent.KeyPress and self._handle_tool_key(event.key(), event.text()):
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _is_typed_value_key(self, key: int, text: str) -> bool:
        return self.composition.transform_controller.active and (
            key == Qt.Key_Backspace or (len(text) == 1 and text in "0123456789.-")
        )

    def _type_transform_value(self, key: int, text: str) -> None:
        transform = self.composition.transform_controller
        current = transform.typed_value_text
        typed = current[:-1] if key == Qt.Key_Backspace else current + text
        result = transform.set_typed_value(typed)
        if not result.success:
            return  # e.g. a second decimal point: ignore the key
        self._consume_result(
            "transform.pointer",
            self._update_transform(self.viewport.last_pointer_position),
        )

    def _other_tool_active(self) -> str:
        """Name of a tool that owns the pointer right now (so measuring cannot start), or ''."""

        if self.composition.transform_controller.active:
            return "move or rotate"
        if self.composition.region_controller.session.active:
            return "region tool"
        return ""

    def _section_planes_selected(self) -> bool:
        ids = self.composition.selection_controller.snapshot().ids
        return any(value == NODE_SECTION_PLANES or section_plane_id_from_node(value) is not None for value in ids)

    def _section_tool_visible(self) -> bool:
        """Section planes are drawn and listed only while the Section tool is engaged.

        Engaged by Add/Compute Section (and the other plane commands) or by selecting a plane;
        left again with Esc, by starting another tool, or by selecting something else.
        """

        return self.composition.state.mesh_object is not None and (self._section_tool or self._section_planes_selected())

    def _section_tool_plane(self) -> object | None:
        """The plane G/R act on while the Section tool is engaged and nothing else is selected."""

        state = self.composition.state
        if not self._section_tool or state.mesh_object is None:
            return None
        return get_active_plane(state.section_collection)

    def _enter_section_tool(self) -> None:
        if not self._section_tool:
            self._section_tool = True
            self.tool_modes.enter(
                "section",
                "Section tool: G moves and R rotates the plane, Compute Section cuts the scan. Esc leaves the tool.",
            )

    def _leave_section_tool(self) -> bool:
        """Hide the planes again; True if anything changed."""

        changed = self._section_tool or self._section_planes_selected()
        if self._section_planes_selected():
            self.composition.selection_controller.select_nodes(())
        self._section_tool = False
        if self.tool_modes.state.id == "section":
            self.tool_modes.cancel()
        return changed

    def _handle_tool_key(self, key: int, text: str = "") -> bool:
        if self._is_typed_value_key(key, text):
            self._type_transform_value(key, text)
            return True
        if not self.composition.transform_controller.active and self._surfacing_key(key, text):
            return True
        if key in {Qt.Key_Return, Qt.Key_Enter}:
            if self.composition.transform_controller.active:
                self._dispatch_application_action("transform.confirm")
                return True
            if self.composition.region_controller.session.active:
                self._dispatch_application_action("region.finish")
                return True
            if self.composition.measure_controller.active:
                self._dispatch_application_action("measure.finish")
                return True
        if key == Qt.Key_Escape:
            if self.composition.transform_controller.active:
                self._dispatch_application_action("transform.cancel")
                return True
            if self.composition.region_controller.session.active:
                self._dispatch_application_action("region.finish")
                return True
            measure = self.composition.measure_controller
            if measure.active:
                if measure.cancel_pending():
                    self.set_status_message("Measurement cancelled")
                    self.refresh()
                else:
                    self._dispatch_application_action("measure.finish")
                return True
            if self._leave_section_tool():
                self.set_status_message("Left the Section tool")
                self.refresh()
                return True
        return False

    def _scene_nodes(self) -> tuple[SceneNode, ...]:
        state = self.composition.state
        common = (
            "view.frame_selected",
            "scene.hide_selected",
            "scene.show_selected",
            "scene.isolate_selected",
            "scene.rename_selected",
            "scene.delete_selected",
        )
        nodes: list[SceneNode] = [
            # the root row names the project (the dock title already says "Scene")
            SceneNode("scene", self._project_display_name(), kind="root", checkable=False, selectable=False, renameable=False, metadata={"context_actions": ("scene.show_all", "view.frame_all")})
        ]
        if state.mesh_object is not None:
            nodes.append(SceneNode(NODE_MESH, state.mesh_object.name, "mesh", "scene", state.mesh_object.visible, metadata={"context_actions": common}))
        group_defaults = {"checkable": False, "selectable": False, "renameable": False}
        nodes.extend(self._surfacing_nodes())
        if state.mesh_object is None and not _has_scene_content(state):
            nodes.append(
                SceneNode(
                    "scene.empty_hint",
                    "Open a scan to begin",
                    "hint",
                    "scene",
                    **group_defaults,
                )
            )
            return tuple(nodes)

        # Groups only appear once they hold something, so a new project is not a
        # wall of empty folders. Section planes are always offered with a model.
        has_planes = (
            len(state.section_collection.planes) > 1  # the user added planes of their own
            or (bool(state.section_collection.planes) and self._section_tool_visible())
        ) and state.mesh_object is not None
        group_rows = (
            (NODE_SECTION_PLANES, "Section Planes", has_planes, {"context_actions": ("section.add_plane", "scene.show_all")}),
            (NODE_SECTION_RESULTS, "Section Results", bool(state.section_collection.results), {}),
            (NODE_REGIONS, "Regions", state.region_collection.active_region is not None, {}),
        )
        nodes.extend(
            SceneNode(node_id, label, "group", "scene", metadata=metadata, **group_defaults)
            for node_id, label, present, metadata in group_rows
            if present
        )
        nodes.extend(
            SceneNode(section_plane_node_id(plane.id), plane.name, "section_plane", NODE_SECTION_PLANES, plane.visible, metadata={"context_actions": common + ("section.compute",)})
            for plane in state.section_collection.planes
            if has_planes
        )
        nodes.extend(
            SceneNode(section_result_node_id(result.id), result.name, "section_result", NODE_SECTION_RESULTS, result.visible, metadata={"context_actions": common})
            for result in state.section_collection.results
        )
        region = state.region_collection.active_region
        if region is not None:
            nodes.append(SceneNode(region_node_id(region.id), f"{region.name or 'Region'} ({len(region.triangle_indices):,} tris)", "region", NODE_REGIONS, region.visible, metadata={"context_actions": common + ("region.extract_boundary",)}))
        return tuple(nodes)

    def _sync_tree_selection_from_controller(self) -> None:
        """Make the tree (and so the inspector) follow selections made outside it, e.g. viewport picks."""

        current = self._scene_model.selected_ids
        wanted = tuple(self.composition.selection_controller.snapshot().ids) + self._surfacing_selected_nodes()
        if wanted != current:
            self._scene_model.select(wanted)

    def _model_info_text(self) -> str:
        state = self.composition.state
        mesh = state.mesh_object
        if mesh is None:
            return "No model"
        triangles = int(getattr(mesh, "source_triangle_count", 0) or len(mesh.source_mesh.triangles))
        text = f"{mesh.name}  -  {state.units}  -  {triangles:,} triangles"
        spacing = self.viewport.grid.spacing
        if spacing is not None and self.viewport.grid.visible:
            text += f"  -  grid {format_spacing(spacing, state.units)}"
        return text

    def refresh(self) -> None:
        self.set_info_message(self._model_info_text())
        self.viewport.set_left_capture_owner(self._viewport_left_capture_owner())
        self._scene_model.replace(self._scene_nodes())
        self._sync_tree_selection_from_controller()
        self.scene_tree.refresh()
        self.inspector.set_model(PropertyInspectorModel(self._inspector_fields()))
        self._render_scene()
        self._sync_action_state()
        self._refresh_next_steps()
        self._refresh_surfacing_panel()

    def _render_scene(self) -> None:
        """Rebuild the scene snapshot and render it, leaving the side panels alone.

        A Move/Rotate drag only changes the 3D scene, so it calls this directly: rebuilding
        the tree, inspector and next-steps panel on every pointer event cost about 30 ms of
        Qt layout each time and made the drag stutter.
        """

        settings = self.composition.settings.display
        snapshot = self.composition.scene_builder.build(
            self.composition.state,
            options=SceneBuildOptions(
                show_grid=settings.show_grid,
                show_axes=settings.show_axes,
                show_axis_gizmo=settings.show_axis_gizmo,
                show_viewcube=settings.show_viewcube,
                show_normals=settings.show_normals,
                show_section_plane=self._section_tool_visible(),
                display_colors={name: getattr(settings, name) for name in DISPLAY_COLOR_FIELDS},
                region_color=settings.region_selection_color,
                region_edge_color=settings.region_selection_edge_color,
                region_opacity=settings.region_selection_opacity,
            ),
            tool_preview=self._tool_preview(),
            camera_request=self._camera_request,
            object_origin=_active_transform_origin(self.composition.state),
            active_transform_angle_delta=self.composition.transform_controller.angle_delta,
            modeling=self._modeling_scene_input(),
        )
        measure = self.composition.measure_controller
        self.viewport.set_measurements(measure.measurements, measure.pending, self.composition.state.units)
        self.viewport.set_annotations(self._surfacing_annotations(), list(self._sketch2d_lines()))
        diagnostics = self.viewport.render_snapshot(snapshot)
        if diagnostics is None and not self.viewport.is_ready:
            self._diagnostics.setText("Viewport initialization pending; latest scene snapshot retained.")
        self._camera_request = CameraRequest()

    def _refresh_next_steps(self) -> None:
        """Nothing selected: show the Model & Next steps panel; otherwise the inspector."""

        state = self.composition.state
        if self.composition.modeling_controller.active:
            # a surfacing tool's panel replaces both (painted by _refresh_surfacing_panel)
            self.next_steps.setVisible(False)
            self.inspector.setVisible(False)
            return
        has_selection = bool(self._scene_model.selected_ids)
        # hide the outgoing panel first: both visible at once, even briefly, grew the window
        outgoing, incoming = (self.next_steps, self.inspector) if has_selection else (self.inspector, self.next_steps)
        outgoing.setVisible(False)
        incoming.setVisible(True)
        if has_selection:
            return
        guidance = build_guidance(state, selected_curve_count=len(state.model.selected_curve_ids))

        def availability(action_id: str) -> tuple[bool, str]:
            try:
                definition = self._framework_actions.require(action_id)
            except KeyError:
                return False, ""
            return definition.enabled, action_tooltip(definition)

        self.next_steps.set_guidance(guidance, availability, self._recent_projects())

    # --- drag and drop ---------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802 - Qt API
        if event.mimeData().hasUrls() and any(url.isLocalFile() for url in event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 - Qt API
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        event.acceptProposedAction()
        if paths:
            self.open_dropped_file(paths[0])

    def open_dropped_file(self, path: Path) -> bool:
        """Open a dropped file: a project, or a scan (which asks for its units)."""

        suffix = Path(path).suffix.lower()
        if suffix == PROJECT_SUFFIX:
            return self.open_project_path(Path(path))
        if suffix in MESH_SUFFIXES:
            return self.open_model_path(Path(path))
        supported = ", ".join(sorted(MESH_SUFFIXES | {PROJECT_SUFFIX}))
        self.set_status_message(f"Cannot open {Path(path).name}: supported files are {supported}")
        return False

    def _viewport_left_capture_owner(self) -> str | None:
        """Return the one active workflow allowed to consume ordinary left input."""

        if self.composition.transform_controller.active:
            return "transform"
        if self.composition.region_controller.session.active:
            return "region"
        return self._surfacing_capture_owner()

    def _on_scene_synchronized(self, diagnostics: ActorUpdateDiagnostics) -> None:
        warning_text = "\n".join(self._last_project_warnings)
        state = self.viewport.diagnostic_state()
        self._diagnostics.setText(
            "Scene sync: "
            f"created={diagnostics.created}, geometry={diagnostics.geometry_updated}, "
            f"style={diagnostics.style_updated}, reused={diagnostics.reused}, "
            f"removed={diagnostics.removed}; actors={state.actor_count}; "
            f"viewport={state.renderer_size}"
            + (f"\n{warning_text}" if warning_text else "")
        )

    def _on_viewport_ready(self) -> None:
        state = self.viewport.diagnostic_state()
        if state.last_synchronization is None:
            self._diagnostics.setText(
                f"VTK ready: {state.render_window_class}; viewport={state.renderer_size}"
            )

    def _on_viewport_failure(self, message: str) -> None:
        text = str(message)
        _LOG.error("Viewport failure: %s", text)
        self._diagnostics.setText(text)
        self.set_status_message("Viewport failed; open Diagnostics for details.")
        self.show_panel("diagnostics", True)

    def _sync_action_state(self) -> None:
        selection = self.composition.selection_controller.snapshot()
        state = self.composition.state
        context = ActionContext(
            has_scene_objects=bool(self.composition.visibility_controller.all_node_ids()),
            has_scene_selection=selection.has_selection or bool(state.model.selected_ids),
            can_undo=self.composition.undo.can_undo,
            can_redo=self.composition.undo.can_redo,
            mesh_loaded=state.mesh_object is not None,
            selection_count=len(selection.ids) + len(state.model.selected_ids),
            has_section_plane=bool(state.section_collection.planes),
            has_section_result=bool(state.section_collection.results),
            has_region=state.region_collection.active_region is not None,
            can_transform=state.selected_item in {"model", "section_plane"} or self._section_tool_plane() is not None,
            transform_active=self.composition.transform_controller.active,
            region_tool_active=self.composition.region_controller.session.active,
            measure_tool_active=self.composition.measure_controller.active,
            has_measurements=self.composition.measure_controller.has_measurements,
            model_count=len(state.model.entities),
            selected_model_count=len(state.model.selected_ids),
            model_tool_active=self.composition.modeling_controller.active,
            busy=self._executor.busy,
        )
        for app_action in self._application_actions.definitions:
            resolved = app_action.resolve(context)
            reason = "" if resolved.enabled else "; ".join(app_action.unmet_requirements(context))
            self._framework_actions.update(
                app_action.id,
                enabled=resolved.enabled,
                visible=resolved.visible,
                checked=resolved.checked,
                disabled_reason=reason,
            )

    def _inspector_fields(self) -> tuple[FieldDefinition, ...]:
        state = self.composition.state
        selected = self._scene_model.selected_ids
        node_id = selected[0] if len(selected) == 1 else None
        if node_id is None:
            return (
                FieldDefinition("selection", "Selection", "No selection", "readonly", read_only=True),
            )
        model_fields = self._surfacing_inspector_fields(node_id)
        if model_fields is not None:
            return model_fields
        if node_id == NODE_MESH and state.mesh_object is not None:
            mesh = state.mesh_object
            return (
                FieldDefinition("name", "Name", mesh.name),
                FieldDefinition("visible", "Visible", mesh.visible, "checkbox"),
                FieldDefinition("location", "Location", tuple(mesh.location), "vector", group="Transform"),
                FieldDefinition("rotation", "Rotation", tuple(mesh.rotation), "vector", group="Transform"),
                FieldDefinition("scale", "Scale", mesh.scale, "number", group="Transform", minimum=1e-6, maximum=1e6),
                FieldDefinition("triangles", "Display triangles", mesh.display_triangle_count, "readonly", read_only=True, group="Diagnostics"),
            )
        plane_id = section_plane_id_from_node(node_id)
        if plane_id is not None:
            plane = next((item for item in state.section_collection.planes if item.id == plane_id), None)
            if plane is not None:
                return (
                    FieldDefinition("name", "Name", plane.name),
                    FieldDefinition("visible", "Visible", plane.visible, "checkbox"),
                    FieldDefinition("section_axis", "Axis", plane.axis, "combo", options=("X", "Y", "Z")),
                    FieldDefinition("section_offset", "Offset", plane.offset, "number", minimum=-1e12, maximum=1e12),
                )
        result_id = section_result_id_from_node(node_id)
        stored = next((item for item in state.section_collection.results if item.id == result_id), None)
        if stored is not None:
            return (
                FieldDefinition("name", "Name", stored.name),
                FieldDefinition("visible", "Visible", stored.visible, "checkbox"),
                FieldDefinition("result_plane", "Plane", f"{stored.axis} = {stored.offset:g}", "readonly", read_only=True),
                FieldDefinition("result_loops", "Loops", len(stored.result.polylines), "readonly", read_only=True, group="Diagnostics"),
            )
        region = state.region_collection.active_region
        if region is not None and node_id == region_node_id(region.id):
            return (
                FieldDefinition("name", "Name", region.name),
                FieldDefinition("visible", "Visible", region.visible, "checkbox"),
                FieldDefinition("region_threshold", "Threshold", region.threshold_degrees, "slider", minimum=0, maximum=180),
                FieldDefinition("region_max", "Maximum triangles", region.max_triangle_count, "number", minimum=1, maximum=10_000_000, decimals=0, advanced=True),
                FieldDefinition("region_count", "Triangle count", len(region.triangle_indices), "readonly", read_only=True, group="Diagnostics"),
            )
        return (FieldDefinition("selection", "Selection", node_id, "readonly", read_only=True),)

    def _on_inspector_value(self, field_id: str, value: object) -> None:
        node_id = self._scene_model.selected_ids[0] if len(self._scene_model.selected_ids) == 1 else None
        if node_id is None:
            return
        if self._surfacing_inspector_value(node_id, field_id, value):
            return
        if field_id == "name":
            self.composition.selection_controller.select_nodes((node_id,))
            result = self._command_result("scene.rename_selected", {"name": value})
        elif field_id == "visible":
            self.composition.selection_controller.select_nodes((node_id,))
            result = self._command_result(
                "scene.show_selected" if bool(value) else "scene.hide_selected"
            )
        elif field_id in {"location", "rotation", "scale"}:
            mesh = self.composition.state.mesh_object
            if mesh is None:
                return
            result = self._command_result(
                "transform.apply_numeric",
                {
                    "location": value if field_id == "location" else mesh.location,
                    "rotation": value if field_id == "rotation" else mesh.rotation,
                    "scale": value if field_id == "scale" else mesh.scale,
                },
            )
        elif field_id == "section_axis":
            result = self._command_result("section.set_axis", {"axis": value})
        elif field_id == "section_offset":
            result = self._command_result("section.set_offset", {"offset": value})
        elif field_id == "region_threshold":
            result = self._command_result("region.threshold", {"value": value})
        elif field_id == "region_max":
            result = self._command_result("region.max_triangles", {"value": value})
        else:
            return
        self._consume_result(f"inspector.{field_id}", replace_dirty(result))

    def _on_inspector_validation_failed(self, _field_id: str, message: str) -> None:
        self.set_status_message(message)

    def open_model(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(self, "Open Model", "", "Mesh files (*.stl *.obj *.ply)")
        return False if not path else self.open_model_path(Path(path))

    def open_model_path(self, path: Path, units: str | None = None) -> bool:
        """Open a mesh; ``units`` skips the prompt (used by scripts and tests)."""

        if not self._confirm_discard("opening a model"):
            return False
        if units is None:
            units = self._ask_units(
                "Model units",
                f"What length unit are the coordinates of {path.name} in?",
                self.composition.settings.import_settings.default_units,
            )
            if units is None:
                return False
        unit_code = get_unit(units).code
        outcome = {"opened": False}

        def finish(model: object) -> None:
            self._reset_state()
            self.composition.state.units = unit_code
            self._install_model(path, model)
            self.current_project_path = None
            self.composition.undo.clear()
            self.set_project_dirty(False)
            self._camera_request = CameraRequest.frame_all()
            self.set_status_message(f"Loaded {path.name} ({unit_code})")
            self.refresh()
            outcome["opened"] = True

        def fail(exc: BaseException) -> None:
            self._report_error("Model import failed", str(exc))

        started = self._run_background(
            f"Loading {path.name}", self._model_reader(path), finish, fail, error_types=_IMPORT_ERRORS
        )
        return started if self._executor.asynchronous else outcome["opened"]

    def _ask_units(self, title: str, prompt: str, current: str) -> str | None:
        labels = [f"{get_unit(code).label} ({code})" for code in UNIT_CODES]
        index = UNIT_CODES.index(get_unit(current).code)
        choice, accepted = QInputDialog.getItem(self, title, prompt, labels, index, False)
        if not accepted:
            return None
        return UNIT_CODES[labels.index(choice)]

    def show_command_palette(self) -> bool:
        """Open the Ctrl+K palette; the chosen command runs after the popup has closed."""

        self._palette_dialog.open_palette()
        return True

    def _run_palette_action(self, action_id: str) -> None:
        QTimer.singleShot(0, lambda: self._framework_actions.invoke(action_id))

    def set_model_units(self) -> bool:
        """Re-label the model's length unit (does not rescale any geometry)."""

        state = self.composition.state
        chosen = self._ask_units(
            "Set model units",
            "Length unit of the model coordinates (existing numbers are not rescaled):",
            state.units,
        )
        if chosen is None:
            return False
        state.units = chosen
        state.units_assumed = False
        self.set_project_dirty(True)
        self.set_status_message(f"Model units set to {chosen}")
        return True

    def open_project(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "openRetop projects (*.openretop)")
        return False if not path else self.open_project_path(Path(path))

    def open_project_path(self, path: Path) -> bool:
        if not self._confirm_discard("opening a project"):
            return False
        result = self.composition.project_files.open_project(path, progress=self._progress)
        self._close_progress()
        if not result.success or result.project is None:
            self._report_error("Project open failed", result.errors[0].message if result.errors else "Project could not be opened")
            return False
        mesh_path = result.resolved_mesh_path
        read_model = None if mesh_path is None or not mesh_path.exists() else self._model_reader(mesh_path)

        def read() -> tuple[object | None, str | None]:
            if mesh_path is None:
                return None, None
            if read_model is None:
                return None, f"Referenced mesh does not exist: {mesh_path}"
            try:
                return read_model(), None
            except _IMPORT_ERRORS as exc:
                return None, f"Referenced mesh could not be loaded: {exc}"

        outcome = {"opened": False}

        def finish(payload: object) -> None:
            model, mesh_warning = payload  # type: ignore[misc]
            self._reset_state()
            if model is not None:
                self._install_model(mesh_path, model)
            self._finish_open_project(path, result, mesh_warning)
            outcome["opened"] = True

        def fail(exc: BaseException) -> None:
            self._report_error("Project open failed", str(exc))

        started = self._run_background(f"Opening {Path(path).name}", read, finish, fail)
        return started if self._executor.asynchronous else outcome["opened"]

    def _finish_open_project(self, path: Path, result: object, mesh_warning: str | None) -> None:
        restored = restore_project_state(self.composition.state, result.project, settings=self.composition.settings)
        self.composition.modeling_controller.reset()
        model, model_warnings = model_from_dict(result.project.metadata.get(MODEL_PROJECT_KEY))
        for name, points, closed in restored.legacy_curves:
            # curves from the older curve tools: editable Surface Sketch curves now
            model.sketch.add_polyline_curve(points, closed=closed, name=name)
        self.composition.state.model = model
        if restored.selected_scene_ids:
            self.composition.selection_controller.select_nodes(
                restored.selected_scene_ids,
                primary_id=restored.primary_selection_id,
            )
        self.composition.undo.clear()
        self.current_project_path = Path(path)
        self._add_recent_project(path)
        self.set_project_dirty(False)
        warnings = [message.message for message in result.warnings]
        warnings.extend(restored.warnings)
        warnings.extend(model_warnings)
        if mesh_warning:
            warnings.append(mesh_warning)
        self._last_project_warnings = tuple(dict.fromkeys(warnings))  # the same missing scan is reported twice
        self._camera_request = CameraRequest.frame_all()
        self.set_status_message(f"Opened {result.project.name}" + (f" with {len(warnings)} warning(s)" if warnings else ""))
        self.refresh()

    def _model_reader(self, path: Path):
        """Return a callable that reads ``path`` and builds its display proxy.

        The callable touches no widgets or application state, so it can run on a
        worker thread. Settings are read here, on the calling thread.
        """

        quality = normalize_proxy_quality(self.composition.settings.import_settings.default_proxy_quality)
        mesh_import = self.composition.mesh_import
        display_proxy = self.composition.display_proxy

        def read() -> _ModelRead:
            loaded = mesh_import.import_mesh(path)
            return _ModelRead(loaded, display_proxy.build(loaded.mesh, quality=quality))

        return read

    def _run_background(
        self,
        label: str,
        work,
        on_done,
        on_error=None,
        *,
        error_types: tuple[type[BaseException], ...] = (Exception,),
    ) -> bool:
        """Run ``work`` through the executor, then ``on_done(result)`` on the UI thread.

        Returns False without doing anything when another task is running.
        """

        if self._executor.busy:
            self.set_status_message(f"Busy: {self._executor.label}")
            return False

        def done(result: object) -> None:
            self._close_progress()
            on_done(result)

        def failed(exc: BaseException) -> None:
            self._close_progress()
            if on_error is not None and isinstance(exc, error_types):
                on_error(exc)
            else:
                raise exc

        if self._executor.asynchronous:
            self._progress(ProgressEvent("background", "start", label))
        return self._executor.submit(label, work, done, failed)

    def _reject_while_busy(self) -> bool:
        if not self._executor.busy:
            return False
        self.set_status_message(f"Busy: {self._executor.label}")
        return True

    @staticmethod
    def _heavy_label(action_id: str) -> str:
        if action_id == "section.compute":
            return "Computing section"
        return "Building geometry"

    def _install_model(self, path: Path, model: _ModelRead) -> None:
        self._section_tool = False
        self.composition.measure_controller.finish()
        self.composition.measure_controller.clear()
        loaded, proxy = model.loaded, model.proxy
        bounds_min = np.min(loaded.mesh.vertices, axis=0) if len(loaded.mesh.vertices) else np.zeros(3)
        bounds_max = np.max(loaded.mesh.vertices, axis=0) if len(loaded.mesh.vertices) else np.zeros(3)
        self.composition.state.mesh_object = MeshObjectState(
            source_mesh=proxy.source_mesh,
            display_mesh=proxy.display_mesh,
            file_path=Path(path).resolve(),  # the project stores it; a relative path breaks on reopening
            name=loaded.metadata.file_name,
            origin=np.zeros(3),
            location=np.zeros(3),
            rotation=np.zeros(3),
            transform_matrix=np.identity(4),
            source_triangle_count=proxy.source_triangle_count,
            display_triangle_count=proxy.display_triangle_count,
            display_proxy_enabled=proxy.proxy_enabled,
            display_reduction_percent=proxy.reduction_percent,
            proxy_quality=proxy.quality,
            source_bounds_min=bounds_min,
            source_bounds_max=bounds_max,
        )

    def _rebuild_display_proxy(self) -> bool:
        mesh = self.composition.state.mesh_object
        if mesh is None:
            return False
        quality = normalize_proxy_quality(self.composition.settings.import_settings.default_proxy_quality)
        source = mesh.source_mesh
        display_proxy = self.composition.display_proxy

        def apply(proxy: object) -> None:
            mesh.display_mesh = proxy.display_mesh
            mesh.display_triangle_count = proxy.display_triangle_count
            mesh.display_proxy_enabled = proxy.proxy_enabled
            mesh.display_reduction_percent = proxy.reduction_percent
            mesh.proxy_quality = proxy.quality
            self.refresh()

        return self._run_background(
            "Rebuilding display mesh",
            lambda: display_proxy.build(source, quality=quality),
            apply,
        )

    def save_project(self, *, as_dialog: bool = False) -> bool:
        path = self.current_project_path
        if as_dialog or path is None:
            selected, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "openRetop projects (*.openretop)")
            path = Path(selected) if selected else None
        if path is None:
            self.set_status_message("Save project cancelled")
            return False
        selection = self.composition.selection_controller.snapshot()
        state = self.composition.state
        active_plane = get_active_plane(state.section_collection)
        project = project_from_app_state(
            mesh_object=state.mesh_object,
            proxy_quality=self.composition.settings.import_settings.default_proxy_quality,
            show_grid=self.composition.settings.display.show_grid,
            show_axes=self.composition.settings.display.show_axes,
            show_normals=self.composition.settings.display.show_normals,
            display_colors={name: getattr(self.composition.settings.display, name) for name in DISPLAY_COLOR_FIELDS},
            section_axis=getattr(active_plane, "axis", "Z"),
            section_offset=getattr(active_plane, "offset", 0.0),
            show_section_plane=any(item.visible for item in state.section_collection.planes),
            section_collection=state.section_collection,
            region_collection=state.region_collection,
            selected_scene_ids=selection.ids,
            primary_selection_id=selection.primary_id,
            units=state.units,
            units_assumed=state.units_assumed,
        )
        model = model_to_dict(state.model)  # surfaces, bodies and the Surface Sketch (S-12)
        if model is not None:
            project.metadata[MODEL_PROJECT_KEY] = model
        project.name = path.stem
        result = self.composition.project_files.save_project(project, path, progress=self._progress)
        self._close_progress()
        if not result.success:
            self._report_error("Project save failed", result.errors[0].message)
            return False
        self.current_project_path = path
        self._add_recent_project(path)
        self.set_project_dirty(False)
        self.set_status_message(f"Project saved: {path}")
        return True

    def _default_shortcuts(self) -> dict[str, str]:
        defaults = {definition.id: definition.shortcut or "" for definition in self._application_actions.definitions}
        defaults.update({action_id: shortcut or "" for action_id, _label, _category, shortcut, _text in _FILE_ACTIONS})
        return defaults

    def show_preferences(self) -> bool:
        defaults = self._default_shortcuts()
        commands = tuple(
            CommandShortcut(definition.id, definition.label, definition.category, defaults.get(definition.id, ""))
            for definition in self._framework_actions.definitions
            if not definition.id.startswith("file.recent.")
        )
        dialog = PreferencesDialog(self.composition.settings, self, commands=commands)
        if not dialog.exec():
            return False
        candidate = dialog.settings
        # every command's key as the saved settings define it (defaults + the user's changes)
        choices = {**defaults, **shortcut_overrides(candidate.keybinds, candidate.future)}
        conflicts = shortcut_conflicts(choices)
        if conflicts:
            labels = ", ".join(f"{key}: {' / '.join(ids)}" for key, ids in conflicts.items())
            self._report_error("Preferences invalid", f"Duplicate keybindings: {labels}")
            return False
        result = self.composition.settings_repository.write(candidate)
        if not result.success:
            self._report_error("Preferences save failed", result.errors[0].message)
            return False
        self.composition.settings = candidate
        self.composition.workflow.settings = candidate
        for action_id, shortcut in choices.items():
            self._framework_actions.update(action_id, shortcut=shortcut or None)
        self.resize(candidate.ui.window_width, candidate.ui.window_height)
        self.set_status_message("Preferences saved")
        self.refresh()
        return True

    def new_project(self) -> bool:
        if not self._confirm_discard("starting a new project"):
            return False
        self._reset_state()
        self.current_project_path = None
        self.composition.undo.clear()
        self.set_project_dirty(False)
        self.set_status_message("Project ready: Untitled Project")
        self.refresh()
        return True

    def _reset_state(self) -> None:
        self._section_tool = False
        fresh = AppState()
        for field in fields(AppState):
            setattr(self.composition.state, field.name, copy.deepcopy(getattr(fresh, field.name)))
        self.composition.region_controller.session.exit()
        self.composition.modeling_controller.reset()
        self.composition.mesh_query_service.invalidate()
        self._last_project_warnings = ()

    def set_project_dirty(self, value: bool = True) -> None:
        self.project_dirty = bool(value)
        self._update_window_title()

    def _on_tool_mode_changed(self, state: object) -> None:
        instructions = str(getattr(state, "instructions", "") or "")
        active = getattr(state, "phase", "inactive") not in {"inactive", "finished"}
        viewport = getattr(self, "viewport", None)
        if viewport is not None:
            viewport.set_tool_hint(instructions if active else "")

    def _project_display_name(self) -> str:
        path = getattr(self, "current_project_path", None)
        return path.stem if path is not None else "Untitled project"

    def _update_window_title(self) -> None:
        if self.current_project_path is None and not self.project_dirty:
            self.setWindowTitle("openRetop V3")
            return
        name = self.current_project_path.name if self.current_project_path else "Untitled Project"
        self.setWindowTitle(f"openRetop V3 — {name}{' *' if self.project_dirty else ''}")

    def _confirm_discard(self, action: str) -> bool:
        if not self.project_dirty:
            return True
        answer = QMessageBox.question(
            self,
            "Unsaved Project",
            f"Save changes before {action}?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if answer == QMessageBox.Cancel:
            return False
        if answer == QMessageBox.Save:
            return self.save_project()
        return True

    def _remember_workspace(self, workspace_id: str) -> None:
        self.composition.settings.future["workspace"] = workspace_id

    def closeEvent(self, event: object) -> None:
        if self._executor.busy:
            self.set_status_message(f"Busy: {self._executor.label} - wait for it to finish before closing.")
            event.ignore()
            return
        if not self._confirm_discard("exiting"):
            event.ignore()
            return
        settings = self.save_framework_settings()
        self.composition.settings.ui.window_width = self.width()
        self.composition.settings.ui.window_height = self.height()
        self.composition.settings.future["workbench_layout"] = settings.to_json()
        self.composition.settings_repository.write(self.composition.settings)
        # Closing a parent QMainWindow hides its child viewport but does not send
        # the child a close event.  Run the viewport's single shutdown path while
        # the native Win32 surface is still valid so VTK observers, overlay
        # resources, and the QVTK interactor are released deterministically.
        self.viewport.close()
        self.composition.modeling_controller.shutdown()
        event.accept()

    def _progress(self, event: ProgressEvent) -> None:
        if self._progress_dialog is None:
            self._progress_dialog = QProgressDialog(event.message, "", 0, 0, self)
            self._progress_dialog.setWindowTitle("openRetop V3")
            self._progress_dialog.setCancelButton(None)
            self._progress_dialog.setMinimumDuration(0)
        self._progress_dialog.setLabelText(event.message)
        if event.total is not None:
            self._progress_dialog.setRange(0, event.total)
            self._progress_dialog.setValue(event.completed)
        QApplication.processEvents()

    def _close_progress(self) -> None:
        if self._progress_dialog is not None:
            self._progress_dialog.close()
            self._progress_dialog.deleteLater()
            self._progress_dialog = None

    def _report_error(self, title: str, message: str) -> None:
        self.set_status_message(title)
        self._diagnostics.setText(message)
        QMessageBox.critical(self, title, message)

    def _recent_projects(self) -> tuple[str, ...]:
        values = self.composition.settings.future.get("recent_projects", [])
        if not isinstance(values, list):
            return ()
        return tuple(str(value) for value in values[:5] if str(value))

    def _add_recent_project(self, path: Path) -> None:
        value = str(Path(path).resolve(strict=False))
        recent = [item for item in self._recent_projects() if item != value]
        self.composition.settings.future["recent_projects"] = [value, *recent][:5]
        self.composition.settings_repository.write(self.composition.settings)

    def _tool_preview(self) -> ToolPreviewState:
        sketch_preview = self._surfacing_tool_preview()
        return ToolPreviewState() if sketch_preview is None else sketch_preview


def _menu_category(action_id: str, category: str) -> str:
    if action_id.startswith("view."):
        return "View"
    if action_id.startswith("edit."):
        return "Edit"
    if action_id in {"section.add_plane", "region.start"}:
        return "Create"
    if action_id.startswith("scene."):
        return "Edit"
    if category in {"Transform", "Sections", "Regions"}:
        return "Modify"
    return category if category in {"File", "Edit", "View", "Create", "Modify", "Inspect", "Help"} else "Modify"


def _node_id_for_pick(pick: SceneObjectPickResult) -> str | None:
    object_id = pick.object_id
    if not object_id:
        return None
    converters = {
        "mesh": lambda _value: NODE_MESH,
        "region": region_node_id,
        "section_plane": section_plane_node_id,
        "section_result": section_result_node_id,
        "model_face": _model_node_for_actor,
        "model_edges": _model_node_for_actor,
    }
    convert = converters.get(str(pick.object_type))
    return None if convert is None else convert(object_id)


def _model_node_for_actor(object_id: str) -> str | None:
    """'model-face:<id>' / 'model-edges:<id>' actors belong to model entity <id>."""

    kind, _sep, entity_id = str(object_id).partition(":")
    if kind == "sketch-curve" and entity_id:
        return f"sketch:{entity_id}"
    return model_node_id(entity_id) if kind in ("model-face", "model-edges") and entity_id else None


def _has_scene_content(state: AppState) -> bool:
    return bool(
        state.model.entities
        or state.model.sketch.curves
        or state.section_collection.results
        or state.region_collection.active_region is not None
    )


def _active_transform_origin(state: AppState) -> tuple[float, float, float] | None:
    """Return the active target origin in world coordinates for overlays."""

    session = state.transform_state
    if session is None:
        return None
    if session.selected_item == "section_plane":
        plane = next(
            (
                item
                for item in state.section_collection.planes
                if item.id == session.section_plane_id
            ),
            None,
        )
        values = None if plane is None else np.asarray(plane_origin(plane), dtype=float)
    else:
        mesh = state.mesh_object
        if mesh is None:
            return None
        return transformed_object_origin(
            getattr(mesh, "origin", None),
            getattr(mesh, "transform_matrix", None),
            location=getattr(mesh, "location", None),
        )
    if values is None or not np.all(np.isfinite(values)):
        return None
    return tuple(float(value) for value in np.asarray(values, dtype=float).reshape(3))


def replace_dirty(result: CommandResult) -> CommandResult:
    if not result.success or not result.changed or result.dirty:
        return result
    return CommandResult(
        success=result.success,
        status=result.status,
        warnings=result.warnings,
        errors=result.errors,
        changed=result.changed,
        dirty=True,
        viewport_requests=result.viewport_requests,
        ui_requests=result.ui_requests,
        undo_payload=result.undo_payload,
        metadata=result.metadata,
    )


def run_v3_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = OpenRetopV3Window(executor=ThreadedExecutor())
    window.show()
    if not window.viewport.start() and window.viewport.last_error:
        window._on_viewport_failure(window.viewport.last_error)
    return app.exec()


run_app = run_v3_app


__all__ = ("OpenRetopV3Window", "run_app", "run_v3_app")
