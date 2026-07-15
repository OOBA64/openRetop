"""openRetop V3 PySide6 workbench using the reusable UI framework."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
from typing import Iterable

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from application.actions import ActionContext, create_core_action_registry
from application.scene_ids import (
    NODE_BREP_SURFACES,
    NODE_CURVES,
    NODE_MESH,
    NODE_REGIONS,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    NODE_SURFACES,
    curve_node_id,
    region_node_id,
    section_plane_node_id,
    section_result_node_id,
    surface_node_id,
)
from application.state import MeshObjectState
from bootstrap import ApplicationComposition, create_application
from project.project_state import project_from_app_state
from viewer.scene_types import CameraRequest

from workbench_ui import (
    ActionDefinition,
    ActionRegistry,
    ApplicationShell,
    CommandPaletteWidget,
    MenuItem,
    MenuSchema,
    PanelDescriptor,
    PropertyInspectorModel,
    PropertyInspectorWidget,
    SceneNode,
    SceneTreeModel,
    SceneTreeWidget,
    ToolInstructionBar,
)
from presentation.qt.viewport import QtSceneViewport


class OpenRetopV3Window(ApplicationShell):
    """Supported V3 shell; controllers and snapshots remain toolkit-neutral."""

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
            parent=parent,
        )
        self.setWindowTitle("openRetop V3")
        self.resize(1440, 900)
        self._camera_request = CameraRequest()
        self.current_project_path: Path | None = None
        self._scene_model = SceneTreeModel()
        self.scene_tree = SceneTreeWidget(self._scene_model, self)
        self.scene_tree.selection_changed.connect(self._on_tree_selection)
        self.scene_tree.visibility_changed.connect(self._on_tree_visibility)
        self.viewport = QtSceneViewport(self)
        self.inspector = PropertyInspectorWidget(PropertyInspectorModel(), self)
        self.palette = CommandPaletteWidget(self._framework_actions, self)
        self.palette.action_triggered.connect(self._dispatch_framework_action)
        self.instructions = ToolInstructionBar(self.tool_modes, self)
        self._diagnostics = QLabel("", self)
        self.add_panel(PanelDescriptor("scene", "Scene", area="left"), self.scene_tree)
        self.add_panel(PanelDescriptor("properties", "Properties", area="right"), self.inspector)
        self.add_panel(PanelDescriptor("commands", "Command Palette", area="bottom"), self.palette)
        diagnostics = QWidget(self)
        diagnostics_layout = QVBoxLayout(diagnostics)
        diagnostics_layout.addWidget(self._diagnostics)
        self.add_panel(PanelDescriptor("diagnostics", "Diagnostics", area="bottom", visible=False), diagnostics)
        self.set_workspace(self.viewport)
        self.statusBar().addPermanentWidget(self.instructions)
        self.refresh()

    def _make_framework_actions(self) -> ActionRegistry:
        registry = ActionRegistry()
        for definition in self._application_actions.definitions:
            registry.register(
                ActionDefinition(
                    id=definition.id,
                    label=definition.label,
                    category=definition.category,
                    description=definition.description,
                    shortcut=definition.shortcut,
                    checkable=definition.checkable,
                    dispatch=lambda _payload, action_id=definition.id: self._dispatch_application_action(action_id),
                )
            )
        custom = (
            ("file.open_model", "Open Model", "File"),
            ("file.open_project", "Open Project", "File"),
            ("file.save_project", "Save Project", "File"),
            ("file.save_project_as", "Save Project As", "File"),
            ("file.export_step", "Export STEP", "File"),
            ("view.front", "Front View", "View"),
            ("view.isometric", "Isometric View", "View"),
        )
        for action_id, label, category in custom:
            registry.register(
                ActionDefinition(
                    action_id,
                    label,
                    category=category,
                    dispatch=lambda _payload, action_id=action_id: self._dispatch_framework_action(action_id),
                )
            )
        return registry

    def _menu_schemas(self) -> tuple[MenuSchema, ...]:
        categories = ("File", "Edit", "View", "Create", "Modify", "Inspect", "Help")
        result: list[MenuSchema] = []
        for category in categories:
            ids = [item.id for item in self._framework_actions.definitions if item.category == category]
            if category == "File":
                ids = ["file.open_model", "file.open_project", "file.save_project", "file.save_project_as", *ids]
            if category == "View":
                ids.extend(["view.front", "view.isometric"])
            unique_ids = tuple(dict.fromkeys(ids))
            result.append(MenuSchema(category, tuple(MenuItem(action_id=item) for item in unique_ids)))
        return tuple(result)

    def _dispatch_application_action(self, action_id: str) -> object:
        if action_id == "view.frame_all":
            self._camera_request = CameraRequest.frame_all()
            self.refresh()
            return True
        if action_id == "view.frame_selected":
            self._camera_request = CameraRequest.frame_selected()
            self.refresh()
            return True
        if action_id == "scene.show_all":
            result = self.composition.visibility_controller.show_all()
            self.set_status_message(result.status or "All scene items visible")
            self.refresh()
            return result.success
        if action_id == "scene.toggle_visibility":
            ids = self.composition.selection_controller.snapshot().ids
            result = self.composition.visibility_controller.toggle(ids)
            self.set_status_message(result.status or "Visibility changed")
            self.refresh()
            return result.success
        if action_id == "edit.undo":
            command = self.composition.undo.undo()
            self.set_status_message(f"Undid {command.name}" if command else "Nothing to undo")
            self.refresh()
            return command is not None
        if action_id == "edit.redo":
            command = self.composition.undo.redo()
            self.set_status_message(f"Redid {command.name}" if command else "Nothing to redo")
            self.refresh()
            return command is not None
        self.set_status_message(f"{self._application_actions.require(action_id).label} is available through the V3 controller layer.")
        return True

    def _dispatch_framework_action(self, action_id: str) -> object:
        if action_id == "file.open_model":
            return self.open_model()
        if action_id == "file.open_project":
            return self.open_project()
        if action_id == "file.save_project":
            return self.save_project()
        if action_id == "file.save_project_as":
            return self.save_project(as_dialog=True)
        if action_id == "view.front":
            if self.viewport.camera_controller is not None:
                self.viewport.camera_controller.set_named_view("front")
                self.viewport.render()
            return True
        if action_id == "view.isometric":
            if self.viewport.camera_controller is not None:
                self.viewport.camera_controller.set_named_view("isometric")
                self.viewport.render()
            return True
        return self._dispatch_application_action(action_id)

    def _on_tree_selection(self, selection: object) -> None:
        ids = tuple(getattr(selection, "ids", ()))
        result = self.composition.selection_controller.select_nodes(ids)
        self.set_status_message(result.status or "Selection changed")
        self.refresh()

    def _on_tree_visibility(self, node_id: str, visible: bool) -> None:
        result = self.composition.visibility_controller.set_visibility((node_id,), visible)
        self.set_status_message(result.status or "Visibility changed")
        self.refresh()

    def _scene_nodes(self) -> tuple[SceneNode, ...]:
        state = self.composition.state
        nodes: list[SceneNode] = [SceneNode("scene", "Scene", kind="root", renameable=False)]
        if state.mesh_object is not None:
            nodes.append(SceneNode(NODE_MESH, state.mesh_object.name, "mesh", "scene", state.mesh_object.visible))
        nodes.append(SceneNode(NODE_SECTION_PLANES, "Section Planes", "group", "scene", renameable=False))
        nodes.extend(
            SceneNode(section_plane_node_id(plane.id), plane.name, "section_plane", NODE_SECTION_PLANES, plane.visible)
            for plane in state.section_collection.planes
        )
        nodes.append(SceneNode(NODE_SECTION_RESULTS, "Section Results", "group", "scene", renameable=False))
        nodes.extend(
            SceneNode(section_result_node_id(result.id), result.name, "section_result", NODE_SECTION_RESULTS, result.visible)
            for result in state.section_collection.results
        )
        nodes.append(SceneNode(NODE_CURVES, "Curves", "group", "scene", renameable=False))
        nodes.extend(
            SceneNode(curve_node_id(curve.id), curve.name, "curve", NODE_CURVES, curve.visible)
            for curve in state.curve_collection.curves
        )
        nodes.append(SceneNode(NODE_SURFACES, "Preview Surfaces", "group", "scene", renameable=False))
        nodes.extend(
            SceneNode(surface_node_id(surface.id), surface.name, "surface", NODE_SURFACES, surface.visible)
            for surface in state.surface_collection.surfaces
        )
        nodes.append(SceneNode(NODE_BREP_SURFACES, "BREP Surfaces", "group", "scene", renameable=False))
        nodes.extend(
            SceneNode(surface_node_id(surface.id), surface.name, "brep_surface", NODE_BREP_SURFACES, surface.visible)
            for surface in state.brep_surface_collection.surfaces
        )
        nodes.append(SceneNode(NODE_REGIONS, "Regions", "group", "scene", renameable=False))
        region = state.region_collection.active_region
        if region is not None:
            nodes.append(SceneNode(region_node_id(region.id), region.name, "region", NODE_REGIONS, region.visible))
        return tuple(nodes)

    def refresh(self) -> None:
        self._scene_model.replace(self._scene_nodes())
        self.scene_tree.refresh()
        snapshot = self.composition.scene_builder.build(
            self.composition.state,
            camera_request=self._camera_request,
            object_origin=(
                None
                if self.composition.state.mesh_object is None
                else self.composition.state.mesh_object.origin
            ),
        )
        diagnostics = self.viewport.render_snapshot(snapshot)
        if diagnostics is not None:
            self._diagnostics.setText(
                "Scene sync: "
                f"created={diagnostics.created}, geometry={diagnostics.geometry_updated}, "
                f"reused={diagnostics.reused}, removed={diagnostics.removed}"
            )
        self._camera_request = CameraRequest()
        self._sync_action_state()

    def _sync_action_state(self) -> None:
        selection = self.composition.selection_controller.snapshot()
        state = self.composition.state
        context = ActionContext(
            has_scene_objects=bool(self._scene_model.nodes),
            has_scene_selection=selection.has_selection,
            can_undo=self.composition.undo.can_undo,
            can_redo=self.composition.undo.can_redo,
            mesh_loaded=state.mesh_object is not None,
            selection_count=len(selection.ids),
            has_section_plane=bool(state.section_collection.planes),
            has_section_result=bool(state.section_collection.results),
            has_curves=bool(state.curve_collection.curves),
            selected_curve_count=len(state.curve_collection.selected_curve_ids),
            selected_surface_count=len(state.surface_collection.selected_surface_ids),
            selected_brep_count=len(state.brep_surface_collection.selected_surface_ids),
            has_region=state.region_collection.active_region is not None,
            cad_available=self.composition.cad.capabilities.available,
        )
        for app_action in self._application_actions.definitions:
            resolved = app_action.resolve(context)
            self._framework_actions.update(
                app_action.id,
                enabled=resolved.enabled,
                visible=resolved.visible,
                checked=resolved.checked,
            )

    def open_model(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(self, "Open Model", "", "Mesh files (*.stl *.obj *.ply)")
        if not path:
            self.set_status_message("Open model cancelled")
            return False
        try:
            loaded = self.composition.mesh_import.import_mesh(path)
            proxy = self.composition.display_proxy.build(
                loaded.mesh,
                quality=self.composition.settings.import_settings.default_proxy_quality,
            )
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
            self._camera_request = CameraRequest.frame_all()
            self.set_status_message(f"Loaded {loaded.metadata.file_name}")
            self.refresh()
            return True
        except (OSError, RuntimeError, ValueError, SystemExit) as exc:
            self.set_status_message(f"Model import failed: {exc}")
            return False

    def open_project(self) -> bool:
        path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "openRetop projects (*.openretop)")
        if not path:
            self.set_status_message("Open project cancelled")
            return False
        result = self.composition.project_files.open_project(path)
        if not result.success or result.project is None:
            self.set_status_message(result.errors[0].message if result.errors else "Project could not be opened")
            return False
        if result.resolved_mesh_path is not None and result.resolved_mesh_path.exists():
            self._load_model_path(result.resolved_mesh_path)
        self.current_project_path = Path(path)
        self.set_status_message(f"Opened {result.project.name}")
        return True

    def _load_model_path(self, path: Path) -> None:
        loaded = self.composition.mesh_import.import_mesh(path)
        proxy = self.composition.display_proxy.build(
            loaded.mesh,
            quality=self.composition.settings.import_settings.default_proxy_quality,
        )
        bounds_min = np.min(loaded.mesh.vertices, axis=0) if len(loaded.mesh.vertices) else np.zeros(3)
        bounds_max = np.max(loaded.mesh.vertices, axis=0) if len(loaded.mesh.vertices) else np.zeros(3)
        self.composition.state.mesh_object = MeshObjectState(
            proxy.source_mesh,
            proxy.display_mesh,
            path,
            loaded.metadata.file_name,
            np.zeros(3),
            np.zeros(3),
            np.zeros(3),
            transform_matrix=np.identity(4),
            source_triangle_count=proxy.source_triangle_count,
            display_triangle_count=proxy.display_triangle_count,
            display_proxy_enabled=proxy.proxy_enabled,
            display_reduction_percent=proxy.reduction_percent,
            proxy_quality=proxy.quality,
            source_bounds_min=bounds_min,
            source_bounds_max=bounds_max,
        )
        self._camera_request = CameraRequest.frame_all()
        self.refresh()

    def save_project(self, *, as_dialog: bool = False) -> bool:
        path = self.current_project_path
        if as_dialog or path is None:
            selected, _ = QFileDialog.getSaveFileName(self, "Save Project", "", "openRetop projects (*.openretop)")
            path = Path(selected) if selected else None
        if path is None:
            self.set_status_message("Save project cancelled")
            return False
        state = self.composition.state
        project = project_from_app_state(
            mesh_object=state.mesh_object,
            proxy_quality=self.composition.settings.import_settings.default_proxy_quality,
            show_grid=self.composition.settings.display.show_grid,
            show_axes=self.composition.settings.display.show_axes,
            show_normals=self.composition.settings.display.show_normals,
            section_axis="Z",
            section_offset=0.0,
            show_section_plane=False,
            section_collection=state.section_collection,
            curve_collection=state.curve_collection,
            surface_collection=state.surface_collection,
            brep_surface_collection=state.brep_surface_collection,
            loft_feature_collection=state.loft_feature_collection,
            four_boundary_feature_collection=state.four_boundary_feature_collection,
        )
        result = self.composition.project_files.save_project(project, path)
        self.set_status_message("Project saved" if result.success else result.errors[0].message)
        if result.success:
            self.current_project_path = path
        return result.success


def run_v3_app() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = OpenRetopV3Window()
    window.show()
    return app.exec()
