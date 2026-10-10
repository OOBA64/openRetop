"""Central V3 action-to-controller workflow routing.

The service contains no widget, dialog, or VTK actor code. Presentation sends a
stable action ID plus an optional payload and receives a structured result.
"""

from __future__ import annotations

from typing import Mapping

from openretop.application.actions import CORE_ACTIONS
from openretop.application.measure_controller import MeasureController
from openretop.application.modeling_controller import ModelingController
from openretop.application.region_controller import RegionController
from openretop.application.results import CommandResult
from openretop.application.scene_controller import SceneController
from openretop.application.scene_ids import (
    NODE_MESH,
    section_plane_node_id,
    section_result_node_id,
)
from openretop.application.section_controller import SectionController
from openretop.application.selection_controller import SelectionController
from openretop.application.state import AppState
from openretop.application.transform_controller import TransformController
from openretop.application.transform_math import PLANE_CONSTRAINTS
from openretop.application.undo import UndoStack
from openretop.application.visibility_controller import VisibilityController
from openretop.sections.section_state import get_active_plane
from openretop.settings.settings_data import AppSettings

PRESENTATION_ACTION_IDS = frozenset(
    {
        "view.frame_all",
        "view.frame_selected",
        "view.frame_region",
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
        region: RegionController,
        measure: MeasureController,
        modeling: ModelingController,
    ) -> None:
        self.state = state
        self.settings = settings
        self.undo = undo
        self.scene = scene
        self.selection = selection
        self.visibility = visibility
        self.transform = transform
        self.section = section
        self.region = region
        self.measure = measure
        self.modeling = modeling

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

        if action.startswith("region."):
            return self._region_action(action, payload)
        return CommandResult.failure(f"No V3 workflow adapter is registered for {action}.")

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
        if action == "region.threshold":
            return self.region.configure(threshold_degrees=float(payload.get("value", 20.0)))
        if action == "region.max_triangles":
            return self.region.configure(max_triangle_count=int(payload.get("value", 50_000)))
        return CommandResult.failure(f"No region adapter is registered for {action}.")

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
            "model.plane_sketch": "plane_sketch",
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
        if action == "model.section_edit":
            entity = payload.get("entity")
            return modeling.section_edit_entity(None if entity is None else str(entity))
        if action == "model.section_profile_edit":
            value = payload.get("value")
            return modeling.section_edit(str(payload.get("operation", "")), None if value is None else float(value))  # type: ignore[arg-type]
        if action == "model.section_fit":
            return modeling.section_fit()
        if action == "model.sketch2d_tool":
            return modeling.sketch2d_tool(str(payload.get("tool", "")))
        if action == "model.sketch2d_plane":
            offset = payload.get("offset")
            plane = payload.get("plane")
            return modeling.sketch2d_set_plane(None if plane is None else str(plane), offset=None if offset is None else float(offset))  # type: ignore[arg-type]
        if action == "model.sketch2d_constrain":
            return modeling.sketch2d_constrain(str(payload.get("kind", "")))
        if action == "model.sketch2d_dimension":
            value = payload.get("value")
            kind = payload.get("kind")
            return modeling.sketch2d_dimension(None if value is None else float(value), None if kind is None else str(kind))  # type: ignore[arg-type]
        if action == "model.sketch2d_set_dimension":
            return modeling.sketch2d_set_dimension(str(payload.get("constraint", "")), float(payload.get("value", 0.0)))  # type: ignore[arg-type]
        if action == "model.sketch2d_delete_constraint":
            return modeling.sketch2d_delete_constraint(str(payload.get("constraint", "")))
        if action == "model.sketch2d_delete":
            return modeling.sketch2d_delete()
        if action == "model.sketch2d_construction":
            return modeling.sketch2d_construction()
        if action == "model.sketch2d_finish":
            return modeling.sketch2d_finish()
        if action == "model.resize":
            changes = payload.get("changes") or {}
            return modeling.resize_surface(str(payload.get("entity", "")), dict(changes))  # type: ignore[arg-type]
        if action == "model.edit_feature":
            changes = {key: value for key, value in payload.items() if key != "feature"}
            return modeling.edit_feature(str(payload.get("feature", "")), **changes)
        if action == "model.rebuild":
            return modeling.rebuild()
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

    def _transformed_mesh(self):
        return None if self.state.mesh_object is None else self.transform.transformed_source_mesh()

    def _display_mesh(self):
        return None if self.state.mesh_object is None else self.state.mesh_object.display_mesh

def _point2(value: object) -> tuple[int, int]:
    values = tuple(value) if isinstance(value, (tuple, list)) else ()
    if len(values) != 2:
        raise ValueError("mouse_start must contain two coordinates.")
    return int(values[0]), int(values[1])


def _optional_float(value: object) -> float | None:
    return None if value is None else float(value)


__all__ = ("PRESENTATION_ACTION_IDS", "WorkflowService")
