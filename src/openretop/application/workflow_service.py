"""Central V3 action-to-controller workflow routing.

The service contains no widget, dialog, or VTK actor code. Presentation sends a
stable action ID plus an optional payload and receives a structured result.
"""

from __future__ import annotations

import copy
from dataclasses import replace
from typing import Mapping
from uuid import uuid4

import numpy as np

from openretop.application.actions import CORE_ACTIONS
from openretop.application.analysis_controller import AnalysisController
from openretop.application.brep_controller import BrepController
from openretop.application.controller_support import CallbackUndoPayload
from openretop.application.curve_controller import CurveController
from openretop.application.manual_curve_controller import ManualCurveActionResult, ManualCurveController
from openretop.application.measure_controller import MeasureController
from openretop.application.modeling_controller import ModelingController
from openretop.application.region_controller import RegionController
from openretop.application.results import CommandResult, ViewportRequest, ViewportRequestKind
from openretop.application.scene_controller import SceneController
from openretop.application.scene_ids import (
    NODE_MESH,
    curve_node_id,
    section_plane_node_id,
    section_result_node_id,
    surface_node_id,
)
from openretop.application.section_controller import SectionController
from openretop.application.selection_controller import SelectionController
from openretop.application.state import AppState
from openretop.application.surface_controller import SurfaceController
from openretop.application.transform_controller import TransformController
from openretop.application.transform_math import PLANE_CONSTRAINTS
from openretop.application.undo import UndoStack
from openretop.application.visibility_controller import VisibilityController
from openretop.curves.curve_state import (
    StoredCurve,
    add_curve,
    get_selected_curves,
    set_active_curve,
)
from openretop.curves.manual_curve import CURVE_POINT_CORNER, CURVE_POINT_SMOOTH
from openretop.geometry.tolerances import curve_simplify_tolerance
from openretop.sections.section_state import get_active_plane, plane_normal, plane_origin
from openretop.settings.settings_data import AppSettings
from openretop.surfaces.loft_feature import LoftFeatureOptions

PRESENTATION_ACTION_IDS = frozenset(
    {
        "view.frame_all",
        "view.frame_selected",
        "view.frame_region",
        "view.frame_source_curves",
        "view.reset",
        "view.named.top",
        "view.named.bottom",
        "view.named.front",
        "view.named.back",
        "view.named.left",
        "view.named.right",
        "view.named.isometric",
        "view.roll_left",
        "view.roll_right",
    }
)


class WorkflowService:
    """Coordinate the extracted controllers behind stable V3 actions."""

    def __init__(
        self,
        *,
        state: AppState,
        settings: AppSettings,
        undo: UndoStack,
        scene: SceneController,
        selection: SelectionController,
        visibility: VisibilityController,
        transform: TransformController,
        section: SectionController,
        curve: CurveController,
        manual_curve: ManualCurveController,
        region: RegionController,
        measure: MeasureController,
        modeling: ModelingController,
        surface: SurfaceController,
        brep: BrepController,
        analysis: AnalysisController,
    ) -> None:
        self.state = state
        self.settings = settings
        self.undo = undo
        self.scene = scene
        self.selection = selection
        self.visibility = visibility
        self.transform = transform
        self.section = section
        self.curve = curve
        self.manual_curve = manual_curve
        self.region = region
        self.measure = measure
        self.modeling = modeling
        self.surface = surface
        self.brep = brep
        self.analysis = analysis

    @property
    def action_ids(self) -> tuple[str, ...]:
        return tuple(action.id for action in CORE_ACTIONS)

    def dispatch(
        self,
        action_id: str,
        payload: Mapping[str, object] | None = None,
    ) -> CommandResult:
        values = dict(payload or {})
        action = str(action_id)
        if action in PRESENTATION_ACTION_IDS:
            return CommandResult.ok(
                status=action.replace(".", " ").title(),
                metadata={"presentation_action": action},
            )
        result = self._dispatch(action, values)
        if result.success and result.undo_payload is not None and result.changed:
            self.undo.push(result.undo_payload)
        return result

    def _dispatch(self, action: str, payload: dict[str, object]) -> CommandResult:
        selection_ids = self.selection.snapshot().ids
        if action == "edit.undo":
            command = self.undo.undo()
            self.modeling.discard_stale()
            return CommandResult.ok(
                status=f"Undid {command.name}" if command else "Nothing to undo",
                changed=command is not None,
            )
        if action == "edit.redo":
            command = self.undo.redo()
            self.modeling.discard_stale()
            return CommandResult.ok(
                status=f"Redid {command.name}" if command else "Nothing to redo",
                changed=command is not None,
            )

        model_result = self._dispatch_scene_on_model(action, payload, selection_ids)
        if model_result is not None:
            return model_result

        if action == "scene.select_model":
            return self.selection.select_model()
        if action == "scene.select_section_plane":
            return self.selection.select_section_plane()
        if action == "scene.clear_selection":
            return self.selection.clear()
        if action == "scene.delete_mesh":
            return self.scene.delete((NODE_MESH,))
        if action == "scene.toggle_mesh_visibility":
            return self.visibility.toggle((NODE_MESH,))
        if action == "scene.rename_selected":
            if len(selection_ids) != 1 or not str(payload.get("name", "")).strip():
                return CommandResult.failure("Rename requires one selected object and a name.")
            return self.scene.rename(selection_ids[0], payload["name"])
        if action == "scene.delete_selected":
            return self.scene.delete(selection_ids)
        if action == "scene.hide_selected":
            return self.visibility.hide(selection_ids)
        if action == "scene.show_selected":
            return self.visibility.show(selection_ids)
        if action == "scene.set_visibility":
            raw_ids = payload.get("node_ids", ())
            try:
                node_ids = (raw_ids,) if isinstance(raw_ids, str) else tuple(raw_ids)
            except TypeError:
                node_ids = ()
            visible = payload.get("visible")
            if not node_ids or not isinstance(visible, bool):
                return CommandResult.failure(
                    "Set visibility requires node_ids and a boolean visible value."
                )
            return self.visibility.set_visibility(
                node_ids,
                visible,
                operation="Show Visibility" if visible else "Hide Visibility",
            )
        if action == "scene.isolate_selected":
            return self.visibility.isolate(selection_ids)
        if action == "scene.show_all":
            return self.visibility.show_all()
        if action == "scene.toggle_visibility":
            return self.visibility.toggle(selection_ids)
        if action in {
            "scene.select_source_curves",
            "scene.isolate_source_curves",
            "scene.show_source_curves",
        }:
            source_nodes = tuple(curve_node_id(value) for value in self.source_curve_ids())
            if not source_nodes:
                return CommandResult.failure("The active surface has no available source curves.")
            if action == "scene.select_source_curves":
                return self.selection.select_nodes(source_nodes)
            if action == "scene.isolate_source_curves":
                return self.visibility.isolate(source_nodes)
            return self.visibility.show(source_nodes)

        if action == "view.toggle_grid":
            return self._toggle_setting("show_grid", "Grid")
        if action == "view.toggle_axes":
            return self._toggle_setting("show_axes", "Axes")
        if action == "view.toggle_axis_gizmo":
            return self._toggle_setting("show_axis_gizmo", "Axis gizmo")
        if action == "view.toggle_view_controls":
            return self._toggle_setting("show_viewcube", "View controls")
        if action == "view.toggle_normals":
            return self._toggle_setting("show_normals", "Normals")
        if action == "view.proxy_quality":
            quality = str(payload.get("quality", "")).strip()
            if not quality:
                return CommandResult.failure("Display proxy quality is required.")
            self.settings.import_settings.default_proxy_quality = quality
            return CommandResult.ok(
                status=f"Display proxy quality: {quality}", changed=True, dirty=True
            )

        if action in {"transform.move", "transform.rotate"}:
            mouse_start = _point2(payload.get("mouse_start", (0, 0)))
            result = (
                self.transform.start_move(mouse_start=mouse_start)
                if action.endswith("move")
                else self.transform.start_rotate(mouse_start=mouse_start)
            )
            return result
        if action == "transform.confirm":
            return self.transform.commit()
        if action == "transform.cancel":
            return self.transform.cancel()
        if action.startswith("transform.constrain_plane_"):
            excluded = action.rsplit("_", 1)[-1].upper()
            return self.transform.set_axis_constraint(PLANE_CONSTRAINTS.get(excluded, excluded))
        if action.startswith("transform.constrain_"):
            return self.transform.set_axis_constraint(action.rsplit("_", 1)[-1].upper())
        if action == "transform.apply_numeric":
            mesh = self.state.mesh_object
            return self.transform.apply_numeric_transform(
                location=payload.get("location", getattr(mesh, "location", (0, 0, 0))),
                rotation=payload.get("rotation", getattr(mesh, "rotation", (0, 0, 0))),
                scale=payload.get("scale", getattr(mesh, "scale", 1.0)),
            )
        if action == "transform.origin_to_geometry":
            return self.transform.set_origin_to_geometry()
        if action == "transform.origin_to_world":
            return self.transform.move_origin_to_world_origin()
        if action == "transform.center_geometry":
            return self.transform.center_geometry_on_origin()
        if action == "transform.reset":
            return self.transform.reset_object_transform()

        if action.startswith("model."):
            return self._dispatch_model(action, payload)

        if action == "measure.distance":
            return self.measure.start()
        if action == "measure.finish":
            return self.measure.finish()
        if action == "measure.model_size":
            return self.measure.describe_model_size()
        if action == "measure.clear":
            return self.measure.clear()

        if action == "section.add_plane":
            return self.section.add_plane(
                axis=str(payload.get("axis", "Z")),
                offset=float(payload.get("offset", 0.0)),
            )
        if action == "section.delete_plane":
            return self.section.delete_active_section_plane()
        if action == "section.compute":
            mesh = self._transformed_mesh()
            return self.section.compute_section(mesh)
        if action == "section.clear_active":
            return self.section.clear_active_section_result()
        if action == "section.clear_all":
            return self.section.clear_all_section_results()
        if action == "section.set_axis":
            plane = get_active_plane(self.state.section_collection)
            return self.section.set_axis_offset(
                axis=str(payload.get("axis", getattr(plane, "axis", "Z"))),
                offset=float(payload.get("offset", getattr(plane, "offset", 0.0))),
            )
        if action == "section.set_offset":
            return self.section.set_offset(float(payload.get("offset", 0.0)))
        if action == "section.toggle_plane_visibility":
            plane = get_active_plane(self.state.section_collection)
            return (
                CommandResult.failure("No active section plane.")
                if plane is None
                else self.visibility.toggle((section_plane_node_id(plane.id),))
            )
        if action == "section.toggle_result_visibility":
            result_id = self.state.section_collection.active_result_id
            return (
                CommandResult.failure("No active section result.")
                if result_id is None
                else self.visibility.toggle((section_result_node_id(result_id),))
            )

        if action == "curve.join":
            return self.curve.join_selected(tolerance=_optional_float(payload.get("tolerance")))
        if action == "curve.auto_close":
            return self.curve.auto_close_selected(tolerance=_optional_float(payload.get("tolerance")))
        if action == "curve.simplify":
            return self.curve.simplify_selected(tolerance=_optional_float(payload.get("tolerance")))
        if action == "curve.smooth":
            return self.curve.smooth_selected(iterations=int(payload.get("iterations", 2)))
        if action == "curve.project":
            mesh = self._transformed_mesh()
            return self.curve.project_selected_to_mesh(
                mesh,
                source_mesh_name=self._mesh_name(),
                mesh_revision=self._mesh_revision(),
                max_search_distance=_optional_float(payload.get("max_search_distance")),
            )
        if action == "curve.rebuild":
            return self.curve.rebuild_selected(
                target_control_point_count=int(payload.get("control_points", 12)),
                curve_method=str(payload.get("curve_method", "smooth_guide")),
                sample_count=int(payload.get("sample_count", 128)),
            )
        if action == "curve.validate_fill":
            return self.curve.validate_selected_for_fill()
        if action == "curve.validate_loft":
            return self.curve.validate_selected_for_loft()
        if action == "curve.convert_smooth":
            return self._convert_selected_curve_to_smooth()
        if action == "curve.simplify_guide":
            return self._simplify_selected_guide(payload)
        if action in {"curve.hide_selected", "curve.isolate_selected"}:
            nodes = tuple(curve_node_id(item.id) for item in get_selected_curves(self.state.curve_collection))
            return self.visibility.hide(nodes) if action.endswith("hide_selected") else self.visibility.isolate(nodes)
        if action == "curve.show_all":
            return self.visibility.show(
                tuple(curve_node_id(item.id) for item in self.state.curve_collection.curves)
            )
        if action == "curve.select_tiny":
            return self.curve.select_tiny()
        if action == "curve.hide_tiny":
            ids = tuple(
                curve_node_id(item.id)
                for item in self.state.curve_collection.curves
                if item.is_tiny_fragment
            )
            return self.visibility.hide(ids)
        if action == "curve.delete_tiny":
            return self.curve.delete_tiny()
        if action == "curve.delete_selected":
            return self.curve.delete_selected()
        if action == "curve.toggle_visibility":
            return self.visibility.toggle(
                tuple(curve_node_id(item.id) for item in get_selected_curves(self.state.curve_collection))
            )

        if action.startswith("manual_curve."):
            return self._manual_action(action, payload)
        if action.startswith("region."):
            return self._region_action(action, payload)
        if action.startswith("surface."):
            return self._surface_action(action, payload)
        if action == "analysis.refresh":
            return self.analysis.inspect_state()
        if action == "analysis.mesh_deviation":
            if "source_points" not in payload:
                return CommandResult.failure("Mesh deviation requires source points.")
            return self.analysis.compute_deviation(
                payload["source_points"],
                mesh=self._transformed_mesh(),
                mesh_revision=self._mesh_revision(),
                max_distance=_optional_float(payload.get("max_distance")),
                signed=bool(payload.get("signed", False)),
            )
        return CommandResult.failure(f"No V3 workflow adapter is registered for {action}.")

    def _manual_action(self, action: str, payload: dict[str, object]) -> CommandResult:
        controller = self.manual_curve
        if action == "manual_curve.create":
            plane = get_active_plane(self.state.section_collection)
            result = controller.begin_new_curve(
                plane_origin=(0, 0, 0) if plane is None else plane_origin(plane),
                plane_normal=(0, 0, 1) if plane is None else plane_normal(plane),
                plane_type="world_xy" if plane is None else "section_plane",
                plane_label="world XY plane" if plane is None else plane.name,
                source_section_plane_id=None if plane is None else plane.id,
                snap_to_mesh=bool(payload.get("snap_to_mesh", False)),
                # A curve drawn on a scan follows its surface (a spline through the clicked
                # points alone cuts through the inside of a curved scan); turn it off with
                # the "keep on mesh" option. Curves drawn off the scan are never projected.
                keep_curve_on_mesh=bool(payload.get("keep_curve_on_mesh", self.state.mesh_object is not None)),
            )
            return _manual_result(result)
        if action == "manual_curve.edit":
            curve = self._active_curve()
            if curve is None:
                return CommandResult.failure("Select an editable manual curve.")
            return _manual_result(controller.begin_edit_curve(curve))
        if action == "manual_curve.finish":
            result = controller.build_new_curve(
                curve_id=str(payload.get("curve_id", f"curve-{uuid4().hex}")),
                name=str(payload.get("name", self._next_curve_name("Manual Curve"))),
                source_mesh_name=self._mesh_name() or None,
                projection_mesh=self._transformed_mesh(),
                mesh_revision=self._mesh_revision(),
            )
            if result.success and result.created_curve is not None:
                before = copy.deepcopy(self.state.curve_collection)
                add_curve(self.state.curve_collection, result.created_curve)
                set_active_curve(self.state.curve_collection, result.created_curve.id)
                self.state.selected_item = "curve"
                after = copy.deepcopy(self.state.curve_collection)
                controller.exit()
                return replace(
                    _manual_result(result),
                    changed=True,
                    dirty=True,
                    undo_payload=self._collection_undo("Create Manual Curve", before, after),
                )
            return _manual_result(result)
        if action == "manual_curve.apply":
            source = self._active_curve()
            if source is None:
                return CommandResult.failure("No manual curve is being edited.")
            result = controller.build_updated_curve(
                source,
                projection_mesh=self._transformed_mesh(),
                mesh_revision=self._mesh_revision(),
                source_mesh_name=self._mesh_name() or None,
            )
            if result.success and result.updated_curve is not None:
                before = copy.deepcopy(self.state.curve_collection)
                self._replace_curve(result.updated_curve)
                after = copy.deepcopy(self.state.curve_collection)
                controller.exit()
                return replace(
                    _manual_result(result),
                    changed=True,
                    dirty=True,
                    undo_payload=self._collection_undo("Edit Manual Curve", before, after),
                )
            return _manual_result(result)
        operations = {
            "manual_curve.cancel": controller.cancel,
            "manual_curve.remove_last": controller.remove_last_point,
            "manual_curve.toggle_closed": controller.toggle_closed,
            "manual_curve.add_point": controller.activate_add_point,
            "manual_curve.insert_point": controller.activate_insert_point,
            "manual_curve.delete_point": controller.delete_selected_point,
            "manual_curve.point_smooth": lambda: controller.set_selected_point_type(CURVE_POINT_SMOOTH),
            "manual_curve.point_corner": lambda: controller.set_selected_point_type(CURVE_POINT_CORNER),
            "manual_curve.toggle_point_type": self._toggle_manual_point_type,
            "manual_curve.auto_corners": controller.auto_detect_corners,
            "manual_curve.clear_auto_corners": controller.clear_auto_corners,
            "manual_curve.smooth_span": controller.smooth_selected_span,
            "manual_curve.straighten_span": controller.straighten_selected_span,
        }
        if action in operations:
            return _manual_result(operations[action]())
        option_map = {
            "manual_curve.snap_option": "snap_to_mesh",
            "manual_curve.smoothness_option": "smoothness",
            "manual_curve.type_option": "curve_method",
            "manual_curve.sample_count_option": "sample_count",
            "manual_curve.corner_threshold_option": "corner_angle_threshold_degrees",
            "manual_curve.auto_corners_option": "auto_detect_corners",
            "manual_curve.keep_on_mesh_option": "keep_curve_on_mesh",
        }
        if action == "manual_curve.placement_option":
            return CommandResult.ok(status="Manual curve placement follows the active work plane.")
        if action in option_map:
            key = option_map[action]
            value = payload.get("value", payload.get(key))
            if value is None:
                return CommandResult.failure(f"{key} value is required.")
            return _manual_result(controller.configure(**{key: value}))
        return CommandResult.failure(f"No manual-curve adapter is registered for {action}.")

    def _region_action(self, action: str, payload: dict[str, object]) -> CommandResult:
        if action == "region.start":
            return self.region.start()
        if action == "region.recompute":
            return self.region.recompute(mesh=self._display_mesh())
        if action == "region.clear":
            return self.region.clear()
        if action == "region.hide":
            return self.region.hide()
        if action == "region.show":
            return self.region.show()
        if action == "region.delete":
            return self.region.delete()
        if action == "region.rename":
            return self.region.rename(str(payload.get("name", "")))
        if action == "region.finish":
            return self.region.exit(status="Region Select finished")
        if action == "region.extract_boundary":
            return self.region.extract_boundary(self._display_mesh())
        if action == "region.select_boundaries":
            return self.region.select_boundary_curves()
        if action == "region.convert_boundary":
            return self.region.convert_boundary_to_hybrid_guide()
        if action == "region.threshold":
            return self.region.configure(threshold_degrees=float(payload.get("value", 20.0)))
        if action == "region.max_triangles":
            return self.region.configure(max_triangle_count=int(payload.get("value", 50_000)))
        return CommandResult.failure(f"No region adapter is registered for {action}.")

    def _surface_action(self, action: str, payload: dict[str, object]) -> CommandResult:
        if action in {"surface.create_from_curves", "surface.fill"}:
            selected = get_selected_curves(self.state.curve_collection)
            return self.surface.create_fill() if len(selected) == 1 else self.surface.create_loft()
        if action == "surface.loft":
            return self.surface.create_loft()
        if action == "surface.conforming_loft":
            return self.surface.create_mesh_conforming_loft(
                mesh=self._transformed_mesh(),
                mesh_revision=self._mesh_revision(),
                source_mesh_name=self._mesh_name(),
            )
        if action == "surface.boundary_patch":
            return self.surface.create_boundary_patch()
        if action == "surface.four_curve_patch":
            return self.surface.create_four_curve_patch()
        if action == "surface.curve_network":
            return self.surface.create_curve_network_patch()
        if action == "surface.brep_face":
            return self.brep.create_face()
        if action == "surface.region_brep_face":
            region = self.state.region_collection.active_region
            if region is None:
                return CommandResult.failure("Select a region before creating a BREP face.")
            boundaries = [
                item
                for item in self.state.curve_collection.curves
                if str(item.metadata.get("source_region_id", "")) == region.id
            ]
            if not boundaries:
                return CommandResult.failure("Extract the selected region boundary first.")
            return self.brep.create_face(curve_id=boundaries[0].id)
        if action == "surface.brep_loft":
            return self.brep.create_loft()
        if action == "surface.editable_brep_loft":
            return self.brep.create_editable_loft()
        if action == "surface.rebuild_brep":
            return self.brep.rebuild_surface()
        if action == "surface.delete":
            if self.state.brep_surface_collection.selected_surface_ids:
                return self.brep.delete_surface()
            return self.surface.delete_surface()
        if action in {"surface.toggle_visibility", "surface.set_visibility"}:
            surface_id = self._active_surface_id()
            if surface_id is None:
                return CommandResult.failure("Select a surface.")
            if action == "surface.toggle_visibility":
                return self.visibility.toggle((surface_node_id(surface_id),))
            return self.visibility.set_visibility(
                (surface_node_id(surface_id),), bool(payload.get("visible", True))
            )
        if action in {"surface.opacity", "surface.wireframe"}:
            surface_id = self._active_surface_id()
            if surface_id is None:
                return CommandResult.failure("Select a surface.")
            if surface_id in self.state.brep_surface_collection.selected_surface_ids:
                return self.brep.update_surface_display(
                    surface_id,
                    opacity=(float(payload.get("value", 1.0)) if action.endswith("opacity") else None),
                    wireframe_overlay=(bool(payload.get("value", True)) if action.endswith("wireframe") else None),
                )
            return self.surface.update_surface(
                surface_id,
                opacity=(float(payload.get("value", 1.0)) if action.endswith("opacity") else None),
                wireframe_overlay=(bool(payload.get("value", True)) if action.endswith("wireframe") else None),
            )
        if action == "surface.loft_options":
            feature = self._active_loft_feature()
            if feature is None:
                return CommandResult.failure("Select an editable loft feature.")
            options = payload.get("options")
            if not isinstance(options, LoftFeatureOptions):
                return CommandResult.failure("Editable loft options are required.")
            return self.brep.update_loft_feature(feature.id, options=options)
        if action == "surface.rebuild_loft":
            return self.brep.rebuild_loft_feature()
        if action == "surface.edit_source":
            feature = self._active_loft_feature()
            if feature is None or not feature.options.source_curve_ids:
                return CommandResult.failure("The active loft has no source curves.")
            result = self.selection.select_curve(feature.options.source_curve_ids[0])
            if not result.success:
                return result
            return self._manual_action("manual_curve.edit", payload)
        if action in {"surface.reverse_source", "surface.source_up", "surface.source_down"}:
            feature = self._active_loft_feature()
            curve = self._active_curve()
            if feature is None or curve is None:
                return CommandResult.failure("Select a loft source curve.")
            if action == "surface.reverse_source":
                return self.brep.reverse_source_curve(curve.id, feature_id=feature.id)
            return self.brep.reorder_source_curve(
                feature.id,
                curve.id,
                -1 if action.endswith("source_up") else 1,
            )
        if action == "surface.duplicate_loft":
            return self.brep.duplicate_loft_feature()
        if action == "surface.delete_loft":
            return self.brep.delete_loft_feature()
        if action == "surface.rebuild_four_boundary":
            return self.surface.rebuild_four_boundary_feature(
                mesh=self._transformed_mesh(), mesh_revision=self._mesh_revision()
            )
        return CommandResult.failure(f"No surface adapter is registered for {action}.")

    def _dispatch_scene_on_model(
        self, action: str, payload: dict[str, object], selection_ids: tuple[str, ...]
    ) -> CommandResult | None:
        """Scene commands (Delete, H, Shift+H, Alt+H, F2) on selected model surfaces.

        Model items have their own selection, so these used to do nothing while a surface was
        selected. When scene objects are selected too, both are acted on (two undo steps).
        Returns None when the command is not about the model.
        """

        model_ids = tuple(self.state.model.selected_ids)
        modeling = self.modeling
        if action == "scene.show_all":
            shown = modeling.show_all()
            if shown.undo_payload is not None and shown.changed:
                self.undo.push(shown.undo_payload)
            return None  # and the scene's own Show All
        curve_ids = tuple(self.state.model.selected_curve_ids)
        if curve_ids and not model_ids and not selection_ids and action == "scene.delete_selected":
            return modeling.sketch_delete(curve_ids)
        if not model_ids:
            return None
        if action == "scene.rename_selected":
            if selection_ids or len(model_ids) != 1:
                return None
            return modeling.rename(model_ids[0], str(payload.get("name", "")))
        operations = {
            "scene.delete_selected": lambda: modeling.delete(model_ids),
            "scene.hide_selected": lambda: modeling.set_visibility(model_ids, False),
            "scene.show_selected": lambda: modeling.set_visibility(model_ids, True),
            "scene.toggle_visibility": lambda: modeling.set_visibility(model_ids, None),
            "scene.isolate_selected": lambda: modeling.set_visibility(model_ids, True, isolate=True),
        }
        operation = operations.get(action)
        if operation is None:
            return None
        result = operation()
        if selection_ids and action != "scene.isolate_selected":
            kept = [value for value in self.state.model.selected_ids if self.state.model.get(value) is not None]
            self.state.model.selected_ids = []  # the model part is done; now the scene objects
            try:
                other = self._dispatch(action, payload)
            finally:
                self.state.model.selected_ids = kept
            if other.success and other.undo_payload is not None and other.changed:
                self.undo.push(other.undo_payload)
        return result

    def _dispatch_model(self, action: str, payload: dict[str, object]) -> CommandResult:
        modeling = self.modeling
        starts = {
            "model.sketch": "sketch",
            "model.section_sketch": "section",
            "model.extrude": "extrude",
            "model.fit_surface": "fit_surface",
            "model.loft": "loft",
            "model.fill": "fill",
            "model.extend": "extend",
            "model.trim": "trim",
            "model.compare": "compare",
        }
        if action in starts:
            return modeling.start(starts[action])
        if action == "model.finish":
            return modeling.finish()
        if action == "model.sketch_finish":
            return modeling.sketch_finish()
        if action == "model.sketch_close":
            return modeling.sketch_finish(close=True)
        if action == "model.sketch_undo_point":
            return modeling.sketch_undo_point()
        if action == "model.sketch_delete":
            return modeling.sketch_delete()
        if action == "model.sketch_delete_point":
            return modeling.sketch_delete_point(None if payload.get("node") is None else str(payload["node"]))
        if action == "model.sketch_insert_point":
            return modeling.sketch_insert_point(str(payload.get("curve", "")), payload.get("position"))
        if action == "model.sketch_split":
            return modeling.sketch_split(None if payload.get("node") is None else str(payload["node"]))
        if action == "model.sketch_toggle_closed":
            curves = payload.get("curves")
            return modeling.sketch_toggle_closed(None if curves is None else tuple(str(value) for value in curves))  # type: ignore[attr-defined]
        if action == "model.sketch_reverse":
            curves = payload.get("curves")
            return modeling.sketch_reverse(None if curves is None else tuple(str(value) for value in curves))  # type: ignore[attr-defined]
        if action == "model.sketch_options":
            smoothness = payload.get("smoothness")
            feature = payload.get("feature")
            return modeling.sketch_options(
                smoothness=None if smoothness is None else float(smoothness),  # type: ignore[arg-type]
                feature=None if feature is None else bool(feature),
            )
        if action == "model.sketch_loft":
            return modeling.sketch_loft()
        if action == "model.sketch_face":
            fit = payload.get("fit_to_scan")
            return modeling.sketch_face(fit_to_scan=None if fit is None else bool(fit))
        if action == "model.section_plane":
            offset = payload.get("offset")
            plane = str(payload.get("plane") or (modeling.session.section_plane if modeling.session else "XY"))
            return modeling.section_set_plane(plane, offset=None if offset is None else float(offset))  # type: ignore[arg-type]
        if action == "model.extrude_measure":
            return modeling.extrude_measure()
        if action == "model.extrude_preview":
            return modeling.extrude_preview()
        if action == "model.extrude_apply":
            return modeling.extrude_apply()
        if action == "model.section_fit":
            return modeling.section_fit()
        if action == "model.section_create":
            return modeling.section_create()
        if action == "model.configure":
            return modeling.configure(**{str(key): value for key, value in payload.items()})
        if action == "model.select_clear":
            return modeling.clear_selection()
        if action == "model.select_invert":
            return modeling.invert_selection()
        if action == "model.fit_preview":
            return modeling.fit_preview()
        if action == "model.fit_create":
            return modeling.create_from_preview()
        if action == "model.loft_apply":
            curve_ids = payload.get("curve_ids")
            ids = None if curve_ids is None else tuple(str(value) for value in curve_ids)  # type: ignore[attr-defined]
            return modeling.loft(ids, ruled=bool(payload.get("ruled", False)))
        if action == "model.fill_apply":
            return modeling.fill_apply()
        if action == "model.fill_clear":
            return modeling.fill_clear()
        if action == "model.fill_continuity":
            return modeling.fill_set_continuity(int(payload.get("index", -1)), str(payload.get("continuity", "")))  # type: ignore[call-overload]
        if action == "model.extend_apply":
            distance = payload.get("distance")
            return modeling.extend(None, None if distance is None else float(distance))  # type: ignore[arg-type]
        if action == "model.trim_compute":
            return modeling.trim_compute()
        if action == "model.trim_apply":
            return modeling.trim_apply(sew=bool(payload.get("sew", True)))
        if action == "model.compare_apply":
            return modeling.compare()
        if action == "model.compare_clear":
            return modeling.clear_deviation()
        if action == "model.delete_selected":
            return modeling.delete()
        return CommandResult.failure(f"Unknown surfacing action: {action}")

    def _toggle_setting(self, field_name: str, label: str) -> CommandResult:
        value = not bool(getattr(self.settings.display, field_name))
        setattr(self.settings.display, field_name, value)
        return CommandResult.ok(
            status=f"{label}: {'shown' if value else 'hidden'}",
            changed=True,
            dirty=True,
            metadata={"checked": value},
        )

    def source_curve_ids(self) -> tuple[str, ...]:
        active_id = self._active_surface_id()
        if active_id is None:
            return ()
        for surface in (
            *self.state.surface_collection.surfaces,
            *self.state.brep_surface_collection.surfaces,
        ):
            if surface.id == active_id:
                existing = {item.id for item in self.state.curve_collection.curves}
                return tuple(item for item in surface.source_curve_ids if item in existing)
        return ()

    def _active_surface_id(self) -> str | None:
        return (
            self.state.surface_collection.active_surface_id
            or self.state.brep_surface_collection.active_surface_id
        )

    def _active_loft_feature(self):
        feature_id = self.state.loft_feature_collection.active_feature_id
        return next(
            (item for item in self.state.loft_feature_collection.features if item.id == feature_id),
            None,
        )

    def _active_curve(self) -> StoredCurve | None:
        active_id = self.state.curve_collection.active_curve_id
        return next(
            (item for item in self.state.curve_collection.curves if item.id == active_id),
            None,
        )

    def _transformed_mesh(self):
        return None if self.state.mesh_object is None else self.transform.transformed_source_mesh()

    def _display_mesh(self):
        return None if self.state.mesh_object is None else self.state.mesh_object.display_mesh

    def _mesh_name(self) -> str:
        return "" if self.state.mesh_object is None else self.state.mesh_object.name

    def _mesh_revision(self) -> object | None:
        mesh = self.state.mesh_object
        if mesh is None:
            return None
        matrix = getattr(mesh, "transform_matrix", None)
        return (
            id(mesh.source_mesh),
            None if matrix is None else tuple(np.asarray(matrix, dtype=float).reshape(-1)),
        )

    def _convert_selected_curve_to_smooth(self) -> CommandResult:
        source = self._active_curve()
        if source is None:
            return CommandResult.failure("Select one editable curve.")
        result = self.manual_curve.convert_curve_to_smooth(
            source,
            projection_mesh=self._transformed_mesh(),
            mesh_revision=self._mesh_revision(),
        )
        if not result.success or result.updated_curve is None:
            return _manual_result(result)
        before = copy.deepcopy(self.state.curve_collection)
        self._replace_curve(result.updated_curve)
        after = copy.deepcopy(self.state.curve_collection)
        return replace(
            _manual_result(result),
            changed=True,
            dirty=True,
            undo_payload=self._collection_undo("Convert Curve", before, after),
        )

    def _simplify_selected_guide(self, payload: dict[str, object]) -> CommandResult:
        source = self._active_curve()
        if source is None:
            return CommandResult.failure("Select one editable guide curve.")
        result = self.manual_curve.simplify_guide_curve(
            source,
            curve_id=f"curve-{uuid4().hex}",
            name=self._next_curve_name("Reduced Guide Curve"),
            tolerance=_optional_float(payload.get("tolerance"))
            or curve_simplify_tolerance(self.state.units),
            projection_mesh=self._transformed_mesh(),
            mesh_revision=self._mesh_revision(),
        )
        if result.success and result.created_curve is not None:
            before = copy.deepcopy(self.state.curve_collection)
            add_curve(self.state.curve_collection, result.created_curve)
            set_active_curve(self.state.curve_collection, result.created_curve.id)
            after = copy.deepcopy(self.state.curve_collection)
            return replace(
                _manual_result(result),
                changed=True,
                dirty=True,
                undo_payload=self._collection_undo("Reduce Guide Curve", before, after),
            )
        return _manual_result(result)

    def _toggle_manual_point_type(self) -> ManualCurveActionResult:
        index = self.manual_curve.session.selected_control_point_index
        if index is None:
            return ManualCurveActionResult(success=False, status="No control point selected")
        current = self.manual_curve.session.point_types[index]
        return self.manual_curve.set_selected_point_type(
            CURVE_POINT_CORNER if current == CURVE_POINT_SMOOTH else CURVE_POINT_SMOOTH
        )

    def _replace_curve(self, curve: StoredCurve) -> None:
        for index, existing in enumerate(self.state.curve_collection.curves):
            if existing.id == curve.id:
                self.state.curve_collection.curves[index] = curve
                set_active_curve(self.state.curve_collection, curve.id)
                return
        raise ValueError(f"Curve not found: {curve.id}")

    def _collection_undo(self, name: str, before: object, after: object) -> CallbackUndoPayload:
        def restore(snapshot: object) -> None:
            self.state.curve_collection = copy.deepcopy(snapshot)
            self.curve.rebind_state(self.state)

        return CallbackUndoPayload(
            name=name,
            undo_action=lambda: restore(before),
            redo_action=lambda: restore(after),
        )

    def _next_curve_name(self, prefix: str) -> str:
        names = {item.name for item in self.state.curve_collection.curves}
        index = 1
        while f"{prefix} {index}" in names:
            index += 1
        return f"{prefix} {index}"


def _manual_result(result: ManualCurveActionResult) -> CommandResult:
    if not result.success:
        return CommandResult.failure(result.status or "Manual curve command failed.", warnings=result.warnings)
    return CommandResult.ok(
        status=result.status,
        changed=result.changed,
        dirty=result.project_dirty,
        warnings=result.warnings,
        metadata=result.metadata,
        viewport_requests=(
            (ViewportRequest(ViewportRequestKind.REFRESH),)
            if result.needs_viewport_refresh
            else ()
        ),
    )


def _point2(value: object) -> tuple[int, int]:
    values = tuple(value) if isinstance(value, (tuple, list)) else ()
    if len(values) != 2:
        raise ValueError("mouse_start must contain two coordinates.")
    return int(values[0]), int(values[1])


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


__all__ = ("PRESENTATION_ACTION_IDS", "WorkflowService")


def _optional_float(value: object) -> float | None:
    """A payload number, or None when the caller did not supply one."""

    return None if value is None else float(value)
