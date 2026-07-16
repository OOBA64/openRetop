"""Supported openRetop V3 PySide6 workbench."""

from __future__ import annotations

import copy
from dataclasses import fields
import logging
from pathlib import Path
import sys
from typing import Mapping

import numpy as np
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMessageBox,
    QProgressDialog,
    QVBoxLayout,
    QWidget,
)

from application.actions import ActionContext, create_core_action_registry
from application.commands import CommandRequest
from application.controller_support import (
    curve_creation_type,
    is_region_boundary_curve,
    is_repaired_curve,
)
from application.keybindings import shortcut_overrides
from application.results import CommandResult
from application.scene_labels import (
    curve_display_label,
    region_display_label,
    surface_display_label,
)
from application.scene_ids import (
    NODE_BREP_SURFACES,
    NODE_CURVES,
    NODE_CURVE_GROUP_MANUAL,
    NODE_CURVE_GROUP_PROJECTED,
    NODE_CURVE_GROUP_REBUILT,
    NODE_CURVE_GROUP_REGION_BOUNDARIES,
    NODE_CURVE_GROUP_REPAIRED,
    NODE_CURVE_GROUP_UNASSIGNED,
    NODE_FEATURES,
    NODE_FOUR_BOUNDARY_FEATURE,
    NODE_LOFT_FEATURE,
    NODE_MESH,
    NODE_REGIONS,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    NODE_SURFACES,
    curve_group_node_id,
    curve_node_id,
    four_boundary_feature_id_from_node,
    four_boundary_feature_node_id,
    loft_feature_id_from_node,
    loft_feature_node_id,
    region_node_id,
    section_plane_id_from_node,
    section_plane_node_id,
    section_result_id_from_node,
    section_result_node_id,
    surface_id_from_node,
    surface_node_id,
)
from application.state import AppState, MeshObjectState
from application.workflow_service import PRESENTATION_ACTION_IDS
from bootstrap import ApplicationComposition, create_application
from curves.manual_curve import is_manual_curve_like, parse_manual_curve_metadata_v2
from infrastructure.io_services import ProgressEvent
from mesh.display_proxy import normalize_proxy_quality
from project.project_session import restore_project_state
from project.project_state import project_from_app_state
from sections.section_state import get_active_plane
from settings.settings_data import DISPLAY_COLOR_FIELDS
from surfaces.brep_state import BREP_TYPE_LOFT_SURFACE
from surfaces.surface_preview import (
    CLOSED_CURVE_FILL,
    TWO_CURVE_LOFT,
    SurfacePreviewMesh,
    build_surface_preview,
)
from surfaces.surface_state import SurfacePatch
from viewer.scene_builder import SceneBuildOptions
from viewer.picking_service import MeshPickResult, PickingService, SceneObjectPickResult
from viewer.scene_synchronizer import ActorUpdateDiagnostics
from viewer.scene_types import CameraRequest, ToolPreviewState, geometry_revision

from workbench_ui import (
    ActionDefinition,
    ActionRegistry,
    ApplicationShell,
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
    ToolInstructionBar,
    ToolbarItem,
    ToolbarSchema,
)
from presentation.qt.preferences_dialog import PreferencesDialog
from presentation.qt.viewport import QtSceneViewport


_LOG = logging.getLogger(__name__)


_FILE_ACTIONS = (
    ("file.new_project", "New Project", "File", "Ctrl+N"),
    ("file.open_model", "Open Model", "File", "Ctrl+O"),
    ("file.open_project", "Open Project", "File", "Ctrl+Shift+O"),
    ("file.save_project", "Save Project", "File", "Ctrl+S"),
    ("file.save_project_as", "Save Project As", "File", "Ctrl+Shift+S"),
    ("file.export_step", "Export STEP", "File", None),
    ("file.preferences", "Preferences", "Edit", "Ctrl+,"),
    ("file.quit", "Quit", "File", "Alt+F4"),
    ("help.about", "About openRetop V3", "Help", None),
)


class OpenRetopV3Window(ApplicationShell):
    """Qt shell backed only by V3 controllers, services, and scene snapshots."""

    def __init__(
        self,
        composition: ApplicationComposition | None = None,
        *,
        parent: QWidget | None = None,
    ) -> None:
        self.composition = composition or create_application()
        self._application_actions = create_core_action_registry()
        self._framework_actions = self._make_framework_actions()
        super().__init__(
            action_registry=self._framework_actions,
            menu_schemas=self._menu_schemas(),
            toolbar_schemas=self._toolbar_schemas(),
            parent=parent,
        )
        self.resize(
            self.composition.settings.ui.window_width,
            self.composition.settings.ui.window_height,
        )
        self._camera_request = CameraRequest.frame_all()
        self.current_project_path: Path | None = None
        self.project_dirty = False
        self._scene_model = SceneTreeModel()
        self._surface_preview_cache: dict[str, tuple[int, SurfacePreviewMesh]] = {}
        self._progress_dialog: QProgressDialog | None = None
        self._last_project_warnings: tuple[str, ...] = ()

        self.scene_tree = SceneTreeWidget(self._scene_model, self)
        self.scene_tree.selection_changed.connect(self._on_tree_selection)
        self.scene_tree.visibility_changed.connect(self._on_tree_visibility)
        self.scene_tree.renamed.connect(self._on_tree_rename)
        self.scene_tree.context_action_requested.connect(self._on_tree_context_action)
        self.viewport = QtSceneViewport(self)
        self.viewport.pointer_event.connect(self._on_viewport_pointer)
        self.viewport.initialization_failed.connect(self._on_viewport_failure)
        self.viewport.render_failed.connect(self._on_viewport_failure)
        self.viewport.scene_synchronized.connect(self._on_scene_synchronized)
        self.viewport.ready.connect(self._on_viewport_ready)
        if self.viewport.interactor is not None:
            self.viewport.interactor.installEventFilter(self)
        self.inspector = PropertyInspectorWidget(PropertyInspectorModel(), self)
        self.inspector.value_changed.connect(self._on_inspector_value)
        self.inspector.validation_failed.connect(self._on_inspector_validation_failed)
        self.palette = CommandPaletteWidget(self._framework_actions, self)
        self.palette.action_triggered.connect(self._dispatch_framework_action)
        self.instructions = ToolInstructionBar(self.tool_modes, self)
        self._diagnostics = QLabel("", self)
        self._diagnostics.setWordWrap(True)
        self.add_panel(PanelDescriptor("scene", "Scene", area="left"), self.scene_tree)
        self.add_panel(PanelDescriptor("properties", "Properties", area="right"), self.inspector)
        self.add_panel(PanelDescriptor("commands", "Command Palette", area="bottom", visible=False), self.palette)
        diagnostics = QWidget(self)
        diagnostics_layout = QVBoxLayout(diagnostics)
        diagnostics_layout.addWidget(self._diagnostics)
        self.add_panel(PanelDescriptor("diagnostics", "Diagnostics", area="bottom", visible=False), diagnostics)
        self.set_workspace(self.viewport)
        self.statusBar().addPermanentWidget(self.instructions)
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
        for action_id, label, category, shortcut in _FILE_ACTIONS:
            registry.register(
                ActionDefinition(
                    action_id,
                    label,
                    category=category,
                    shortcut=shortcut,
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
        return shortcut_overrides(self.composition.settings.keybinds)

    def _menu_schemas(self) -> tuple[MenuSchema, ...]:
        result: list[MenuSchema] = []
        for category in ("File", "Edit", "View", "Create", "Modify", "Inspect", "Help"):
            ids = [item.id for item in self._framework_actions.definitions if item.category == category]
            result.append(MenuSchema(category, tuple(MenuItem(action_id=value) for value in ids)))
        return tuple(result)

    @staticmethod
    def _toolbar_schemas() -> tuple[ToolbarSchema, ...]:
        return (
            ToolbarSchema(
                "Main",
                tuple(
                    ToolbarItem(value)
                    for value in (
                        "file.open_model",
                        "file.open_project",
                        "file.save_project",
                        "edit.undo",
                        "edit.redo",
                        "view.frame_all",
                        "view.frame_selected",
                        "transform.move",
                        "transform.rotate",
                        "section.add_plane",
                        "manual_curve.create",
                        "region.start",
                    )
                ),
            ),
        )

    def _dispatch_framework_action(
        self,
        action_id: str,
        payload: Mapping[str, object] | None = None,
    ) -> object:
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
        if action_id == "file.export_step":
            return self.export_step()
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
        if action_id in PRESENTATION_ACTION_IDS:
            return self._dispatch_view_action(action_id)
        if action_id == "scene.rename_selected" and not payload:
            selection = self.composition.selection_controller.snapshot()
            if len(selection.ids) != 1:
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
            ids = self.composition.selection_controller.snapshot().ids
            self._camera_request = CameraRequest.frame_selected(ids)
        elif action_id == "view.frame_source_curves":
            result = self._command_result("scene.select_source_curves")
            if not result.success:
                self._consume_result(action_id, result)
                return False
            ids = self.composition.selection_controller.snapshot().ids
            self._camera_request = CameraRequest.frame_selected(ids)
        elif action_id.startswith("view.named."):
            self._camera_request = CameraRequest.named_view(action_id.rsplit(".", 1)[-1])
        else:
            return False
        self.refresh()
        return True

    def _command_result(
        self,
        action_id: str,
        payload: Mapping[str, object] | None = None,
    ) -> CommandResult:
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
        self.refresh()

    def _sync_tool_mode(self, action_id: str, result: CommandResult) -> None:
        if not result.success:
            return
        if action_id in {"manual_curve.create", "manual_curve.edit"}:
            self.tool_modes.enter(
                "manual_curve",
                "Left-click to place/select points. Enter finishes; Esc cancels the current action.",
            )
        elif action_id == "region.start":
            self.tool_modes.enter("region", "Click the mesh to grow a region; Esc finishes.")
        elif action_id in {"transform.move", "transform.rotate"}:
            self.tool_modes.enter("transform", "Move the pointer; Enter confirms and Esc cancels.")
        elif action_id in {"manual_curve.finish", "manual_curve.apply", "region.finish", "transform.confirm"}:
            self.tool_modes.finish()
        elif action_id in {"manual_curve.cancel", "transform.cancel"}:
            self.tool_modes.cancel()

    def _on_tree_selection(self, selection: object) -> None:
        ids = tuple(getattr(selection, "ids", ()))
        feature_ids = [value for value in ids if _is_feature_node(value)]
        ordinary_ids = [value for value in ids if not _is_feature_node(value)]
        if feature_ids:
            self._activate_feature(feature_ids[0])
        result = self.composition.selection_controller.select_nodes(ordinary_ids)
        if not ordinary_ids and feature_ids:
            result = CommandResult.ok(status="Selected editable feature")
        self.set_status_message(result.status or "Selection changed")
        self.refresh()

    def _activate_feature(self, node_id: str) -> None:
        loft_id = loft_feature_id_from_node(node_id)
        if loft_id is not None:
            self.composition.state.loft_feature_collection.active_feature_id = loft_id
            feature = next((item for item in self.composition.state.loft_feature_collection.features if item.id == loft_id), None)
            if feature and feature.brep_surface_id:
                self.composition.selection_controller.select_surface(feature.brep_surface_id)
            return
        four_id = four_boundary_feature_id_from_node(node_id)
        if four_id is not None:
            self.composition.state.four_boundary_feature_collection.active_feature_id = four_id
            feature = next((item for item in self.composition.state.four_boundary_feature_collection.features if item.id == four_id), None)
            if feature and feature.preview_surface_id:
                self.composition.selection_controller.select_surface(feature.preview_surface_id)

    def _on_tree_visibility(self, node_id: str, visible: bool) -> None:
        selected = self.composition.selection_controller.select_nodes((node_id,))
        if not selected.success:
            self._consume_result("tree.visibility", selected)
            return
        result = self._command_result(
            "scene.show_selected" if visible else "scene.hide_selected"
        )
        self._consume_result("tree.visibility", replace_dirty(result))

    def _on_tree_rename(self, node_id: str, name: str) -> None:
        self.composition.selection_controller.select_nodes((node_id,))
        result = self._command_result("scene.rename_selected", {"name": name})
        self._consume_result("scene.rename_selected", replace_dirty(result))

    def _on_tree_context_action(self, action_id: str, context: object) -> None:
        ids = tuple(getattr(context, "ids", ()))
        feature_ids = tuple(value for value in ids if _is_feature_node(value))
        if feature_ids:
            self._activate_feature(feature_ids[0])
        ordinary_ids = tuple(value for value in ids if value not in feature_ids)
        if ordinary_ids:
            self.composition.selection_controller.select_nodes(ordinary_ids)
        self._dispatch_framework_action(action_id)

    def _on_viewport_pointer(
        self,
        event_name: str,
        x_position: int,
        y_position: int,
        pick: object,
    ) -> None:
        if self.composition.transform_controller.active:
            if event_name == "motion":
                result = self.composition.transform_controller.update(
                    (x_position, y_position),
                    camera=self.viewport.camera_vectors(),
                    model_bounds=self.viewport.model_bounds(),
                    fine=bool(
                        self.viewport.interactor is not None
                        and self.viewport.interactor.GetShiftKey()
                    ),
                )
                self._consume_result("transform.pointer", result)
            return

        manual = self.composition.manual_curve_controller
        if manual.session.active:
            self._route_manual_pointer(event_name, x_position, y_position, pick)
            return

        region = self.composition.region_controller
        if region.session.active:
            gesture = region.handle_pointer_event(event_name, x_position, y_position)
            if event_name == "left_release" and bool(gesture.metadata.get("is_click")):
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

        if event_name == "left_release" and isinstance(pick, SceneObjectPickResult) and pick.hit:
            node_id = _node_id_for_pick(pick)
            if node_id is not None:
                result = self.composition.selection_controller.select_nodes((node_id,))
                self.set_status_message(result.status or "Selection changed")
                self.refresh()

    def _route_manual_pointer(
        self,
        event_name: str,
        x_position: int,
        y_position: int,
        pick: object,
    ) -> None:
        controller = self.composition.manual_curve_controller
        session = controller.session
        projected = self.viewport.project_points(session.control_points)
        point_pick = PickingService.pick_control_point(
            (x_position, y_position), projected, session.control_points
        )
        dragged = (
            controller.update_drag_state(x_position, y_position)
            if event_name == "motion"
            else session.left_dragged
        )
        route = controller.route_pointer_event(
            event_name,
            button="left" if event_name.startswith("left") else None,
            control_point_index=(
                point_pick.control_point_index if point_pick.hit else None
            ),
            dragged=dragged,
            press_position=(x_position, y_position),
        )
        if not route.consumed:
            return
        point, snapped, triangle_index, normal = self._manual_pointer_point(
            x_position, y_position, pick
        )
        result = None
        if route.action == "preview":
            result = controller.set_preview(
                point=point,
                valid=point is not None,
                snaps_to_mesh=snapped,
                triangle_index=triangle_index,
                normal=normal,
            )
        elif route.action == "move_point" and point is not None:
            result = controller.move_drag_candidate(
                point,
                snapped=snapped,
                triangle_index=triangle_index,
                normal=normal,
            )
        elif route.action == "add_point" and point is not None:
            result = controller.append_point(
                point,
                snapped=snapped,
                triangle_index=triangle_index,
                normal=normal,
            )
        elif route.action == "insert_point" and point is not None:
            result = controller.insert_point(
                controller.insert_index_for_point(point),
                point,
                snapped=snapped,
                triangle_index=triangle_index,
                normal=normal,
            )
        elif route.action == "select_point":
            result = controller.select_point(route.control_point_index)
        elif route.action == "clear_preview":
            result = controller.clear_preview()
        if result is not None:
            if result.status:
                self.set_status_message(result.status)
            if result.project_dirty:
                self.set_project_dirty(True)
            if result.needs_viewport_refresh or result.changed:
                self.refresh()
        elif route.action not in {"none", "finish_drag"}:
            self.refresh()

    def _manual_pointer_point(
        self, x_position: int, y_position: int, pick: object
    ) -> tuple[object | None, bool, int | None, object | None]:
        if isinstance(pick, MeshPickResult) and pick.hit:
            return pick.position, True, pick.triangle_index, pick.normal
        session = self.composition.manual_curve_controller.session
        if session.snap_to_mesh:
            return None, False, None, None
        point = self.viewport.point_on_plane(
            x_position,
            y_position,
            plane_origin=session.plane_origin,
            plane_normal=session.plane_normal,
        )
        return point, False, None, session.plane_normal

    def keyPressEvent(self, event: object) -> None:
        if self._handle_tool_key(event.key()):
            event.accept()
            return
        super().keyPressEvent(event)

    def eventFilter(self, watched: object, event: object) -> bool:
        if (
            watched is self.viewport.interactor
            and event.type() == QEvent.KeyPress
            and self._handle_tool_key(event.key())
        ):
            event.accept()
            return True
        return super().eventFilter(watched, event)

    def _handle_tool_key(self, key: int) -> bool:
        if key in {Qt.Key_Return, Qt.Key_Enter}:
            manual = self.composition.manual_curve_controller.session
            if manual.active:
                self._dispatch_application_action(
                    "manual_curve.apply" if manual.editing else "manual_curve.finish"
                )
                return True
            if self.composition.transform_controller.active:
                self._dispatch_application_action("transform.confirm")
                return True
            if self.composition.region_controller.session.active:
                self._dispatch_application_action("region.finish")
                return True
        if key == Qt.Key_Escape:
            if self.composition.transform_controller.active:
                self._dispatch_application_action("transform.cancel")
                return True
            if self.composition.manual_curve_controller.session.active:
                self._dispatch_application_action("manual_curve.cancel")
                return True
            if self.composition.region_controller.session.active:
                self._dispatch_application_action("region.finish")
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
            SceneNode("scene", "Scene", kind="root", renameable=False, metadata={"context_actions": ("scene.show_all", "view.frame_all")})
        ]
        if state.mesh_object is not None:
            nodes.append(SceneNode(NODE_MESH, state.mesh_object.name, "mesh", "scene", state.mesh_object.visible, metadata={"context_actions": common}))
        nodes.extend(
            (
                SceneNode(NODE_SECTION_PLANES, "Section Planes", "group", "scene", renameable=False, metadata={"context_actions": ("section.add_plane", "scene.show_all")}),
                SceneNode(NODE_SECTION_RESULTS, "Section Results", "group", "scene", renameable=False),
                SceneNode(NODE_CURVES, "Curves", "group", "scene", renameable=False),
                SceneNode(NODE_SURFACES, "Preview Surfaces", "group", "scene", renameable=False),
                SceneNode(NODE_BREP_SURFACES, "BREP Surfaces", "group", "scene", renameable=False),
                SceneNode(NODE_REGIONS, "Regions", "group", "scene", renameable=False),
                SceneNode(NODE_FEATURES, "Editable Features", "group", "scene", renameable=False),
            )
        )
        nodes.extend(
            SceneNode(section_plane_node_id(plane.id), plane.name, "section_plane", NODE_SECTION_PLANES, plane.visible, metadata={"context_actions": common + ("section.compute",)})
            for plane in state.section_collection.planes
        )
        nodes.extend(
            SceneNode(section_result_node_id(result.id), result.name, "section_result", NODE_SECTION_RESULTS, result.visible, metadata={"context_actions": common})
            for result in state.section_collection.results
        )
        curve_groups = (
            (NODE_CURVE_GROUP_UNASSIGNED, "Unassigned"),
            (NODE_CURVE_GROUP_MANUAL, "Manual"),
            (NODE_CURVE_GROUP_REGION_BOUNDARIES, "Region Boundaries"),
            (NODE_CURVE_GROUP_REPAIRED, "Repaired"),
            (NODE_CURVE_GROUP_PROJECTED, "Projected"),
            (NODE_CURVE_GROUP_REBUILT, "Rebuilt"),
        )
        nodes.extend(SceneNode(node_id, label, "curve_group", NODE_CURVES, renameable=False) for node_id, label in curve_groups)
        nodes.extend(
            SceneNode(curve_group_node_id(result.id), result.name, "curve_group", NODE_CURVES, renameable=False)
            for result in state.section_collection.results
        )
        result_ids = {item.id for item in state.section_collection.results}
        for curve in state.curve_collection.curves:
            parent = _curve_parent(curve, result_ids)
            nodes.append(SceneNode(curve_node_id(curve.id), curve_display_label(curve), "curve", parent, curve.visible, metadata={"context_actions": common + ("curve.toggle_visibility",)}))
        nodes.extend(
            SceneNode(surface_node_id(surface.id), surface_display_label(surface), "surface", NODE_SURFACES, surface.visible, metadata={"context_actions": common + ("surface.toggle_visibility",)})
            for surface in state.surface_collection.surfaces
        )
        nodes.extend(
            SceneNode(surface_node_id(surface.id), surface_display_label(surface), "brep_surface", NODE_BREP_SURFACES, surface.visible, metadata={"context_actions": common + ("surface.rebuild_brep", "file.export_step")})
            for surface in state.brep_surface_collection.surfaces
        )
        region = state.region_collection.active_region
        if region is not None:
            nodes.append(SceneNode(region_node_id(region.id), region_display_label(region), "region", NODE_REGIONS, region.visible, metadata={"context_actions": common + ("region.extract_boundary",)}))
        nodes.extend(
            SceneNode(loft_feature_node_id(feature.id), feature.name, NODE_LOFT_FEATURE, NODE_FEATURES, metadata={"context_actions": ("surface.rebuild_loft", "surface.duplicate_loft", "surface.delete_loft")})
            for feature in state.loft_feature_collection.features
        )
        nodes.extend(
            SceneNode(four_boundary_feature_node_id(feature.id), feature.name, NODE_FOUR_BOUNDARY_FEATURE, NODE_FEATURES, metadata={"context_actions": ("surface.rebuild_four_boundary",)})
            for feature in state.four_boundary_feature_collection.features
        )
        return tuple(nodes)

    def refresh(self) -> None:
        self._scene_model.replace(self._scene_nodes())
        self.scene_tree.refresh()
        self.inspector.set_model(PropertyInspectorModel(self._inspector_fields()))
        previews = self._surface_previews()
        active_surface_id = (
            self.composition.state.surface_collection.active_surface_id
            or self.composition.state.brep_surface_collection.active_surface_id
        )
        source_ids = self.composition.workflow.source_curve_ids()
        settings = self.composition.settings.display
        snapshot = self.composition.scene_builder.build(
            self.composition.state,
            options=SceneBuildOptions(
                show_grid=settings.show_grid,
                show_axes=settings.show_axes,
                show_axis_gizmo=settings.show_axis_gizmo,
                show_normals=settings.show_normals,
                show_section_plane=True,
                display_colors={name: getattr(settings, name) for name in DISPLAY_COLOR_FIELDS},
                region_color=settings.region_selection_color,
                region_edge_color=settings.region_selection_edge_color,
                region_opacity=settings.region_selection_opacity,
            ),
            surface_previews=previews,
            tool_preview=self._tool_preview(),
            camera_request=self._camera_request,
            active_surface_id=active_surface_id,
            surface_source_curve_ids=source_ids,
            object_origin=None if self.composition.state.mesh_object is None else self.composition.state.mesh_object.origin,
            active_transform_angle_delta=self.composition.transform_controller.angle_delta,
        )
        diagnostics = self.viewport.render_snapshot(snapshot)
        if diagnostics is None and not self.viewport.is_ready:
            self._diagnostics.setText("Viewport initialization pending; latest scene snapshot retained.")
        self._camera_request = CameraRequest()
        self._sync_action_state()

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
        selected_curves = [item for item in state.curve_collection.curves if item.id in state.curve_collection.selected_curve_ids]
        selected_curve = selected_curves[0] if len(selected_curves) == 1 else None
        manual = self.composition.manual_curve_controller.session
        active_surface = self._active_surface_record()
        context = ActionContext(
            has_scene_objects=bool(self.composition.visibility_controller.all_node_ids()),
            has_scene_selection=selection.has_selection,
            can_undo=self.composition.undo.can_undo,
            can_redo=self.composition.undo.can_redo,
            mesh_loaded=state.mesh_object is not None,
            selection_count=len(selection.ids),
            has_section_plane=bool(state.section_collection.planes),
            has_section_result=bool(state.section_collection.results),
            has_curves=bool(state.curve_collection.curves),
            selected_curve_count=len(selected_curves),
            selected_curve_closed=bool(selected_curve and selected_curve.is_closed),
            selected_curve_open=bool(selected_curve and not selected_curve.is_closed),
            selected_curve_editable=bool(selected_curve and is_manual_curve_like(selected_curve)),
            selected_surface_count=len(state.surface_collection.selected_surface_ids),
            selected_brep_count=len(state.brep_surface_collection.selected_surface_ids),
            has_region=state.region_collection.active_region is not None,
            has_loft_feature=state.loft_feature_collection.active_feature_id is not None,
            has_source_curves=bool(active_surface and active_surface.source_curve_ids),
            can_transform=state.selected_item in {"model", "section_plane"},
            transform_active=self.composition.transform_controller.active,
            manual_curve_active=manual.active,
            manual_curve_idle=not manual.active,
            manual_curve_creating=manual.active and not manual.editing,
            manual_curve_editing=manual.editing,
            can_add_manual_point=manual.active,
            has_manual_control_point=manual.selected_control_point_index is not None,
            region_tool_active=self.composition.region_controller.session.active,
            has_region_boundary_curves=any(is_region_boundary_curve(item) for item in state.curve_collection.curves),
            selected_region_boundary_curve=bool(selected_curve and is_region_boundary_curve(selected_curve)),
            cad_available=self.composition.cad.capabilities.available,
            has_runtime_brep=bool(self.composition.brep_controller.runtime_objects),
        )
        for app_action in self._application_actions.definitions:
            resolved = app_action.resolve(context)
            self._framework_actions.update(app_action.id, enabled=resolved.enabled, visible=resolved.visible, checked=resolved.checked)

    def _inspector_fields(self) -> tuple[FieldDefinition, ...]:
        state = self.composition.state
        selected = self._scene_model.selected_ids
        node_id = selected[0] if len(selected) == 1 else None
        if node_id is None:
            return (
                FieldDefinition("selection", "Selection", "No selection", "readonly", read_only=True),
                FieldDefinition("cad", "CAD backend", self.composition.cad.capabilities.backend_name, "readonly", read_only=True, group="Diagnostics"),
            )
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
        curve_id = node_id.split(":", 1)[1] if node_id.startswith("curve:") else None
        if curve_id is not None:
            curve = next((item for item in state.curve_collection.curves if item.id == curve_id), None)
            if curve is not None:
                values = [
                    FieldDefinition("name", "Name", curve.name),
                    FieldDefinition("visible", "Visible", curve.visible, "checkbox"),
                    FieldDefinition("closed", "Closed", curve.is_closed, "readonly", read_only=True),
                    FieldDefinition("point_count", "Point count", curve.point_count, "readonly", read_only=True, group="Diagnostics"),
                    FieldDefinition("length", "Length", curve.length, "readonly", read_only=True, group="Diagnostics"),
                ]
                control = parse_manual_curve_metadata_v2(curve)
                if control is not None:
                    values.extend(
                        (
                            FieldDefinition("manual_method", "Curve method", control.curve_method, "combo", group="Manual Curve", advanced=True, options=("polyline", "smooth_guide", "hybrid")),
                            FieldDefinition("manual_samples", "Sample count", control.sample_count, "number", group="Manual Curve", advanced=True, minimum=8, maximum=4096, decimals=0),
                        )
                    )
                return tuple(values)
        region = state.region_collection.active_region
        if region is not None and node_id == region_node_id(region.id):
            return (
                FieldDefinition("name", "Name", region.name),
                FieldDefinition("visible", "Visible", region.visible, "checkbox"),
                FieldDefinition("region_threshold", "Threshold", region.threshold_degrees, "slider", minimum=0, maximum=180),
                FieldDefinition("region_max", "Maximum triangles", region.max_triangle_count, "number", minimum=1, maximum=10_000_000, decimals=0, advanced=True),
                FieldDefinition("region_count", "Triangle count", len(region.triangle_indices), "readonly", read_only=True, group="Diagnostics"),
            )
        surface_id = surface_id_from_node(node_id)
        if surface_id is not None:
            surface = self._surface_record(surface_id)
            if surface is not None:
                return (
                    FieldDefinition("name", "Name", surface.name),
                    FieldDefinition("visible", "Visible", surface.visible, "checkbox"),
                    FieldDefinition("surface_opacity", "Opacity", float(surface.metadata.get("display_opacity", 0.22)), "number", minimum=0.05, maximum=1.0),
                    FieldDefinition("surface_wireframe", "Wireframe", bool(surface.metadata.get("wireframe_overlay", False)), "checkbox"),
                    FieldDefinition("source_count", "Source curves", len(surface.source_curve_ids), "readonly", read_only=True, group="Diagnostics"),
                )
        loft_id = loft_feature_id_from_node(node_id)
        if loft_id is not None:
            feature = next((item for item in state.loft_feature_collection.features if item.id == loft_id), None)
            if feature is not None:
                return (
                    FieldDefinition("feature_name", "Name", feature.name),
                    FieldDefinition("feature_sources", "Source curves", len(feature.options.source_curve_ids), "readonly", read_only=True),
                    FieldDefinition("feature_overbuild", "Overbuild", feature.options.overbuild_amount, "number", minimum=0, maximum=10, advanced=True),
                    FieldDefinition("feature_status", "Build status", feature.last_build_reason, "readonly", read_only=True, group="Diagnostics"),
                )
        return (FieldDefinition("selection", "Selection", node_id, "readonly", read_only=True),)

    def _on_inspector_value(self, field_id: str, value: object) -> None:
        node_id = self._scene_model.selected_ids[0] if len(self._scene_model.selected_ids) == 1 else None
        if node_id is None:
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
        elif field_id == "surface_opacity":
            result = self._command_result("surface.opacity", {"value": value})
        elif field_id == "surface_wireframe":
            result = self._command_result("surface.wireframe", {"value": value})
        elif field_id == "manual_method":
            result = self._command_result("manual_curve.type_option", {"value": value})
        elif field_id == "manual_samples":
            result = self._command_result("manual_curve.sample_count_option", {"value": int(float(value))})
        else:
            return
        self._consume_result(f"inspector.{field_id}", replace_dirty(result))

    def _on_inspector_validation_failed(self, _field_id: str, message: str) -> None:
        self.set_status_message(message)

    def open_model(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(self, "Open Model", "", "Mesh files (*.stl *.obj *.ply)")
        return False if not path else self.open_model_path(Path(path))

    def open_model_path(self, path: Path) -> bool:
        if not self._confirm_discard("opening a model"):
            return False
        try:
            self._reset_state()
            self._load_model_path(path)
        except (OSError, RuntimeError, ValueError, SystemExit) as exc:
            self._report_error("Model import failed", str(exc))
            return False
        self.current_project_path = None
        self.composition.undo.clear()
        self.set_project_dirty(False)
        self._camera_request = CameraRequest.frame_all()
        self.set_status_message(f"Loaded {path.name}")
        self.refresh()
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
        self._reset_state()
        mesh_warning = None
        if result.resolved_mesh_path is not None:
            if result.resolved_mesh_path.exists():
                try:
                    self._load_model_path(result.resolved_mesh_path)
                except (OSError, RuntimeError, ValueError, SystemExit) as exc:
                    mesh_warning = f"Referenced mesh could not be loaded: {exc}"
            else:
                mesh_warning = f"Referenced mesh does not exist: {result.resolved_mesh_path}"
        restored = restore_project_state(self.composition.state, result.project, settings=self.composition.settings)
        if restored.selected_scene_ids:
            self.composition.selection_controller.select_nodes(
                restored.selected_scene_ids,
                primary_id=restored.primary_selection_id,
            )
        self.composition.brep_controller.runtime_objects.clear()
        self.composition.undo.clear()
        self.current_project_path = Path(path)
        self._add_recent_project(path)
        self.set_project_dirty(False)
        warnings = [message.message for message in result.warnings]
        warnings.extend(restored.warnings)
        if mesh_warning:
            warnings.append(mesh_warning)
        self._last_project_warnings = tuple(warnings)
        self._camera_request = CameraRequest.frame_all()
        self.set_status_message(f"Opened {result.project.name}" + (f" with {len(warnings)} warning(s)" if warnings else ""))
        self.refresh()
        return True

    def _load_model_path(self, path: Path) -> None:
        loaded = self.composition.mesh_import.import_mesh(path, progress=self._progress)
        proxy = self.composition.display_proxy.build(
            loaded.mesh,
            quality=normalize_proxy_quality(self.composition.settings.import_settings.default_proxy_quality),
            progress=self._progress,
        )
        self._close_progress()
        bounds_min = np.min(loaded.mesh.vertices, axis=0) if len(loaded.mesh.vertices) else np.zeros(3)
        bounds_max = np.max(loaded.mesh.vertices, axis=0) if len(loaded.mesh.vertices) else np.zeros(3)
        self.composition.state.mesh_object = MeshObjectState(
            source_mesh=proxy.source_mesh,
            display_mesh=proxy.display_mesh,
            file_path=Path(path),
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
        proxy = self.composition.display_proxy.build(
            mesh.source_mesh,
            quality=normalize_proxy_quality(self.composition.settings.import_settings.default_proxy_quality),
            progress=self._progress,
        )
        self._close_progress()
        mesh.display_mesh = proxy.display_mesh
        mesh.display_triangle_count = proxy.display_triangle_count
        mesh.display_proxy_enabled = proxy.proxy_enabled
        mesh.display_reduction_percent = proxy.reduction_percent
        mesh.proxy_quality = proxy.quality
        self.refresh()
        return True

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
            curve_collection=state.curve_collection,
            region_collection=state.region_collection,
            surface_collection=state.surface_collection,
            brep_surface_collection=state.brep_surface_collection,
            loft_feature_collection=state.loft_feature_collection,
            four_boundary_feature_collection=state.four_boundary_feature_collection,
            selected_scene_ids=selection.ids,
            primary_selection_id=selection.primary_id,
        )
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

    def export_step(self) -> bool:
        selected = self.composition.state.brep_surface_collection.active_surface_id
        runtime = None if selected is None else self.composition.brep_controller.runtime_objects.get(selected)
        if runtime is None:
            self._report_error("STEP export unavailable", "Select and rebuild a BREP surface before export.")
            return False
        path, _ = QFileDialog.getSaveFileName(self, "Export STEP", "", "STEP files (*.step *.stp)")
        if not path:
            return False
        result = self.composition.step_export.export(runtime, path, progress=self._progress)
        self._close_progress()
        if not result.success:
            self._report_error("STEP export failed", result.reason)
            return False
        self.set_status_message(f"Exported STEP: {path}")
        return True

    def show_preferences(self) -> bool:
        dialog = PreferencesDialog(self.composition.settings, self)
        if not dialog.exec():
            return False
        candidate = dialog.settings
        shortcuts = shortcut_overrides(candidate.keybinds)
        owners: dict[str, list[str]] = {}
        for action_id, shortcut in shortcuts.items():
            owners.setdefault(shortcut.casefold(), []).append(action_id)
        conflicts = [values for values in owners.values() if len(values) > 1]
        if conflicts:
            labels = ", ".join(" / ".join(values) for values in conflicts)
            self._report_error("Preferences invalid", f"Duplicate keybindings: {labels}")
            return False
        result = self.composition.settings_repository.write(candidate)
        if not result.success:
            self._report_error("Preferences save failed", result.errors[0].message)
            return False
        self.composition.settings = candidate
        self.composition.workflow.settings = candidate
        for action_id, shortcut in shortcuts.items():
            self._framework_actions.update(action_id, shortcut=shortcut)
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
        fresh = AppState()
        for field in fields(AppState):
            setattr(self.composition.state, field.name, copy.deepcopy(getattr(fresh, field.name)))
        self.composition.manual_curve_controller.cancel()
        self.composition.region_controller.session.exit()
        self.composition.brep_controller.runtime_objects.clear()
        self.composition.mesh_query_service.invalidate()
        self._surface_preview_cache.clear()
        self._last_project_warnings = ()

    def set_project_dirty(self, value: bool = True) -> None:
        self.project_dirty = bool(value)
        self._update_window_title()

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

    def closeEvent(self, event: object) -> None:
        if not self._confirm_discard("exiting"):
            event.ignore()
            return
        settings = self.save_framework_settings()
        self.composition.settings.ui.window_width = self.width()
        self.composition.settings.ui.window_height = self.height()
        self.composition.settings.future["workbench_layout"] = settings.to_json()
        self.composition.settings_repository.write(self.composition.settings)
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

    def _active_surface_record(self):
        active_id = (
            self.composition.state.surface_collection.active_surface_id
            or self.composition.state.brep_surface_collection.active_surface_id
        )
        return self._surface_record(active_id) if active_id else None

    def _surface_record(self, surface_id: str):
        return next(
            (
                item
                for item in (
                    *self.composition.state.surface_collection.surfaces,
                    *self.composition.state.brep_surface_collection.surfaces,
                )
                if item.id == surface_id
            ),
            None,
        )

    def _surface_previews(self) -> tuple[SurfacePreviewMesh, ...]:
        state = self.composition.state
        curves = state.curve_collection.curves
        curve_map = {item.id: item for item in curves}
        records: list[tuple[SurfacePatch, str]] = [
            (item, "preview_surface") for item in state.surface_collection.surfaces if item.visible
        ]
        for brep in state.brep_surface_collection.surfaces:
            if not brep.visible:
                continue
            records.append(
                (
                    SurfacePatch(
                        id=brep.id,
                        name=brep.name,
                        source_curve_ids=list(brep.source_curve_ids),
                        surface_type="preview_loft" if brep.brep_type == BREP_TYPE_LOFT_SURFACE else "preview_fill",
                        visible=brep.visible,
                        selected=brep.selected,
                        metadata={
                            **brep.metadata,
                            "preview_mode": TWO_CURVE_LOFT if brep.brep_type == BREP_TYPE_LOFT_SURFACE else CLOSED_CURVE_FILL,
                        },
                    ),
                    "brep_visual_preview",
                )
            )
        previews: list[SurfacePreviewMesh] = []
        live_ids: set[str] = set()
        for surface, role in records:
            source_curves = [curve_map[value] for value in surface.source_curve_ids if value in curve_map]
            signature = geometry_revision(
                surface.source_curve_ids,
                surface.metadata,
                tuple((curve.id, curve.fitted_points, curve.is_closed) for curve in source_curves),
                surface.selected,
                role,
            )
            cached = self._surface_preview_cache.get(surface.id)
            if cached is not None and cached[0] == signature:
                preview = cached[1]
            else:
                result = build_surface_preview(
                    surface,
                    curves,
                    mesh=None if state.mesh_object is None else self.composition.transform_controller.transformed_source_mesh(),
                    mesh_query_service=self.composition.mesh_query_service,
                    mesh_revision=None if state.mesh_object is None else id(state.mesh_object.source_mesh),
                )
                if result.mesh is None:
                    continue
                source = result.mesh
                preview = SurfacePreviewMesh(
                    vertices=source.vertices,
                    faces=source.faces,
                    source_surface_id=source.source_surface_id,
                    selected=surface.selected,
                    opacity=float(surface.metadata.get("display_opacity", source.opacity or 0.22)),
                    wireframe_overlay=bool(surface.metadata.get("wireframe_overlay", source.wireframe_overlay)),
                    display_role=role,
                    overbuild_handle_points=source.overbuild_handle_points,
                    show_overbuild_handles=source.show_overbuild_handles,
                )
                self._surface_preview_cache[surface.id] = (signature, preview)
            previews.append(preview)
            live_ids.add(surface.id)
        self._surface_preview_cache = {
            key: value for key, value in self._surface_preview_cache.items() if key in live_ids
        }
        return tuple(previews)

    def _tool_preview(self) -> ToolPreviewState:
        controller = self.composition.manual_curve_controller
        session = controller.session
        if session.active:
            display = controller.display_state(
                projection_mesh=None if self.composition.state.mesh_object is None else self.composition.transform_controller.transformed_source_mesh(),
                mesh_revision=None if self.composition.state.mesh_object is None else id(self.composition.state.mesh_object.source_mesh),
            )
            return ToolPreviewState(
                revision=geometry_revision(display.control_points, display.fitted_points, display.preview_point, display.is_closed),
                active=True,
                control_points=display.control_points,
                point_types=tuple(display.point_types or ()),
                fitted_points=display.fitted_points,
                closed=display.is_closed,
                plane_normal=tuple(session.plane_normal),
                snap_to_mesh=display.snap_to_mesh,
                selected_control_point_index=display.selected_point_index,
                curve_method=display.curve_method,
                sample_count=display.sample_count,
                preview_point=None if display.preview_point is None else tuple(display.preview_point),
                preview_valid=display.preview_valid,
                preview_snaps_closed=display.preview_snaps_closed,
                preview_snaps_to_mesh=display.preview_snaps_to_mesh,
            )
        return ToolPreviewState()


def _menu_category(action_id: str, category: str) -> str:
    if action_id.startswith("view."):
        return "View"
    if action_id.startswith("edit."):
        return "Edit"
    if action_id in {
        "section.add_plane",
        "manual_curve.create",
        "region.start",
        "surface.create_from_curves",
        "surface.fill",
        "surface.loft",
        "surface.conforming_loft",
        "surface.boundary_patch",
        "surface.four_curve_patch",
        "surface.curve_network",
        "surface.brep_face",
        "surface.region_brep_face",
        "surface.brep_loft",
        "surface.editable_brep_loft",
    }:
        return "Create"
    if action_id.startswith("analysis."):
        return "Inspect"
    if action_id.startswith("scene."):
        return "Edit"
    if category in {"Transform", "Sections", "Curves", "Manual Curve", "Regions", "Surfaces", "BREP"}:
        return "Modify"
    return category if category in {"File", "Edit", "View", "Create", "Modify", "Inspect", "Help"} else "Modify"


def _node_id_for_pick(pick: SceneObjectPickResult) -> str | None:
    object_id = pick.object_id
    if not object_id:
        return None
    converters = {
        "mesh": lambda _value: NODE_MESH,
        "curve": curve_node_id,
        "surface": surface_node_id,
        "region": region_node_id,
        "section_plane": section_plane_node_id,
        "section_result": section_result_node_id,
    }
    convert = converters.get(str(pick.object_type))
    return None if convert is None else convert(object_id)


def _curve_parent(curve: object, result_ids: set[str]) -> str:
    creation = curve_creation_type(curve)
    if is_manual_curve_like(curve):
        return NODE_CURVE_GROUP_MANUAL
    if is_region_boundary_curve(curve):
        return NODE_CURVE_GROUP_REGION_BOUNDARIES
    if is_repaired_curve(curve):
        return NODE_CURVE_GROUP_REPAIRED
    if creation == "projected_curve":
        return NODE_CURVE_GROUP_PROJECTED
    if creation == "rebuilt_curve":
        return NODE_CURVE_GROUP_REBUILT
    result_id = str(getattr(curve, "section_result_id", ""))
    return curve_group_node_id(result_id) if result_id in result_ids else NODE_CURVE_GROUP_UNASSIGNED


def _is_feature_node(node_id: str) -> bool:
    return node_id.startswith(f"{NODE_LOFT_FEATURE}:") or node_id.startswith(f"{NODE_FOUR_BOUNDARY_FEATURE}:")


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
    window = OpenRetopV3Window()
    window.show()
    if not window.viewport.start() and window.viewport.last_error:
        window._on_viewport_failure(window.viewport.last_error)
    return app.exec()


run_app = run_v3_app


__all__ = ("OpenRetopV3Window", "run_app", "run_v3_app")
