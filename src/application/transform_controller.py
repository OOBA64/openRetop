"""UI-independent controller for numeric and modal object transforms."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import math

import numpy as np

from application.controller_support import (
    CallbackUndoPayload,
    ControllerBase,
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
    publish_scene_change,
)
from application.events import ActiveToolChangedEvent
from application.feature_dependencies import FeatureDependencyChange
from application.results import CommandResult, ViewportRequest
from application.section_controller import (
    SectionWorkflowSnapshot,
    capture_section_workflow_state,
    invalidate_section_plane_dependencies,
    restore_section_workflow_state,
)
from application.state import ActiveTransformState, AppState
from application.transform_math import (
    axis_constrained_camera_move_delta,
    build_object_transform_matrix,
    calculate_geometry_centering_delta,
    calculate_location_for_origin_change,
    calculate_origin_to_world_origin,
    camera_relative_move_delta,
    mesh_rotate_delta,
    normalized_vector,
    rotate_vector_around_axis,
    transform_bounds,
    transform_point,
    world_axis_vector,
)
from mesh.triangle_mesh import TriangleMeshData
from sections.section_state import (
    SectionPlaneState,
    get_active_plane,
    normalize_plane_state,
    plane_normal,
    plane_origin,
    set_plane_origin_normal,
)


SELECT_MODEL = "model"
SELECT_SECTION_PLANE = "section_plane"
TRANSFORM_MOVE = "move"
TRANSFORM_ROTATE = "rotate"
GENERATED_GEOMETRY_TRANSFORM_WARNING = (
    "Generated sections/curves/surfaces will not follow mesh transform. "
    "Recompute after moving."
)


@dataclass(frozen=True, slots=True)
class CameraVectors:
    """Explicit viewport camera basis supplied by a presentation adapter."""

    right: np.ndarray
    up: np.ndarray
    forward: np.ndarray

    def __post_init__(self) -> None:
        object.__setattr__(self, "right", _vector3(self.right, "camera right"))
        object.__setattr__(self, "up", _vector3(self.up, "camera up"))
        object.__setattr__(self, "forward", _vector3(self.forward, "camera forward"))


@dataclass(slots=True)
class ObjectTransformSnapshot:
    """State needed to undo object transforms without copying mesh topology."""

    origin: np.ndarray
    location: np.ndarray
    rotation: np.ndarray
    scale: float
    transform_matrix: np.ndarray | None
    source_bounds_min: np.ndarray | None
    source_bounds_max: np.ndarray | None
    source_vertices: np.ndarray | None = None
    display_vertices: np.ndarray | None = None


class TransformController(ControllerBase):
    """Own transform workflow state while accepting screen/camera data explicitly."""

    def __init__(
        self,
        state: AppState,
        events=None,
        *,
        mesh_query_invalidator: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(state, events)
        if mesh_query_invalidator is not None and not callable(mesh_query_invalidator):
            raise TypeError("mesh_query_invalidator must be callable.")
        self._mesh_query_invalidator = mesh_query_invalidator
        self._last_readout: str | None = None
        self._angle_delta: float | None = None
        self._modal_object_before: ObjectTransformSnapshot | None = None
        self._modal_section_before: SectionWorkflowSnapshot | None = None

    @property
    def last_readout(self) -> str | None:
        return self._last_readout

    @property
    def angle_delta(self) -> float | None:
        return self._angle_delta

    @property
    def active(self) -> bool:
        return self.state.transform_state is not None

    def set_object_transform(
        self,
        *,
        location: object,
        rotation: object,
        scale: object,
    ) -> CommandResult:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        try:
            next_location = _vector3(location, "Location")
            next_rotation = _vector3(rotation, "Rotation")
            next_scale = _positive_number(scale, "Scale")
        except ValueError as exc:
            return CommandResult.failure(str(exc), status="Transform failed")
        if (
            np.allclose(mesh_object.location, next_location, atol=1e-12)
            and np.allclose(mesh_object.rotation, next_rotation, atol=1e-12)
            and math.isclose(float(mesh_object.scale), next_scale, abs_tol=1e-12)
        ):
            return CommandResult.ok(status=self._model_status("Transforms update live"))

        before = self._capture_object()
        mesh_object.location = next_location
        mesh_object.rotation = next_rotation
        mesh_object.scale = next_scale
        self._apply_object_transform()
        after = self._capture_object()
        return self._object_changed_result(
            status=self._model_status("Transforms update live"),
            reason="object_transform_changed",
            undo=self._object_undo("Transform Model", before, after),
        )

    apply_numeric_transform = set_object_transform

    def set_origin_to_geometry(
        self,
        *,
        transformed_bounds: tuple[object, object] | None = None,
    ) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        try:
            minimum, maximum = (
                self.transformed_source_bounds()
                if transformed_bounds is None
                else (
                    _vector3(transformed_bounds[0], "Minimum bound"),
                    _vector3(transformed_bounds[1], "Maximum bound"),
                )
            )
            center = (minimum + maximum) * 0.5
            new_origin = transform_point(np.linalg.inv(self.current_object_matrix()), center)
        except (IndexError, TypeError, ValueError, np.linalg.LinAlgError) as exc:
            return CommandResult.failure(str(exc), status="Set origin failed")
        return self._change_origin(
            new_origin,
            status="Origin set to geometry",
            reason="object_origin_set_to_geometry",
        )

    def move_origin_to_world_origin(self) -> CommandResult:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        before = self._capture_object()
        new_origin, new_location = calculate_origin_to_world_origin(
            mesh_object.origin,
            mesh_object.location,
            mesh_object.rotation,
            mesh_object.scale,
        )
        if (
            np.allclose(mesh_object.origin, new_origin, atol=1e-12)
            and np.allclose(mesh_object.location, new_location, atol=1e-12)
        ):
            return CommandResult.ok(
                status=self._model_status("Origin moved to world origin")
            )
        mesh_object.origin = new_origin
        mesh_object.location = new_location
        self._apply_object_transform()
        after = self._capture_object()
        return self._object_changed_result(
            status=self._model_status("Origin moved to world origin"),
            reason="object_origin_moved_to_world",
            undo=self._object_undo("Move Origin to World", before, after),
        )

    def center_geometry_on_origin(self) -> CommandResult:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        bounds = mesh_object.source_mesh.get_axis_aligned_bounding_box()
        raw_center = np.asarray(bounds.get_center(), dtype=float)
        delta = calculate_geometry_centering_delta(mesh_object.origin, raw_center)
        if np.allclose(delta, np.zeros(3), atol=1e-12):
            return CommandResult.ok(status=self._model_status("Geometry centered on origin"))
        before = self._capture_object(include_geometry=True)
        mesh_object.source_mesh.translate(delta.tolist())
        mesh_object.display_mesh.translate(delta.tolist())
        mesh_object.source_bounds_min = np.asarray(bounds.get_min_bound(), dtype=float) + delta
        mesh_object.source_bounds_max = np.asarray(bounds.get_max_bound(), dtype=float) + delta
        self._apply_object_transform()
        after = self._capture_object(include_geometry=True)
        return self._object_changed_result(
            status=self._model_status("Geometry centered on origin"),
            reason="object_geometry_centered",
            undo=self._object_undo("Center Geometry on Origin", before, after),
        )

    def reset_object_transform(self) -> CommandResult:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        next_location = np.asarray(mesh_object.origin, dtype=float).copy()
        next_rotation = np.zeros(3, dtype=float)
        if (
            np.allclose(mesh_object.location, next_location, atol=1e-12)
            and np.allclose(mesh_object.rotation, next_rotation, atol=1e-12)
            and math.isclose(float(mesh_object.scale), 1.0, abs_tol=1e-12)
        ):
            return CommandResult.ok(
                status=self._model_status(f"Selected: {mesh_object.name}")
            )
        before = self._capture_object()
        mesh_object.location = next_location
        mesh_object.rotation = next_rotation
        mesh_object.scale = 1.0
        self._apply_object_transform()
        after = self._capture_object()
        result = self._object_changed_result(
            status=self._model_status(f"Selected: {mesh_object.name}"),
            reason="object_transform_reset",
            undo=self._object_undo("Reset Object Transform", before, after),
        )
        return CommandResult.ok(
            status=result.status,
            changed=result.changed,
            dirty=result.dirty,
            viewport_requests=(*result.viewport_requests, ViewportRequest.frame_all()),
            ui_requests=result.ui_requests,
            undo_payload=result.undo_payload,
            metadata=result.metadata,
        )

    def start(
        self,
        mode: str,
        *,
        mouse_start: tuple[int, int],
        selected_item: str | None = None,
        section_plane_id: str | None = None,
    ) -> CommandResult:
        mode_key = str(mode).strip().lower()
        if mode_key not in {TRANSFORM_MOVE, TRANSFORM_ROTATE}:
            return CommandResult.failure("Transform mode must be 'move' or 'rotate'.")
        if self.state.transform_state is not None:
            return CommandResult.failure("A transform is already active.")
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        target = self.state.selected_item if selected_item is None else str(selected_item)
        if target not in {SELECT_MODEL, SELECT_SECTION_PLANE}:
            return CommandResult.failure("The current selection cannot be transformed.", status="No selection")
        try:
            start_position = (int(mouse_start[0]), int(mouse_start[1]))
        except (IndexError, TypeError, ValueError):
            return CommandResult.failure("mouse_start must contain two integer coordinates.")

        section_origin = np.zeros(3, dtype=float)
        section_normal = np.asarray([0.0, 0.0, 1.0], dtype=float)
        section_axis = "Z"
        section_offset = 0.0
        plane: SectionPlaneState | None = None
        self._modal_object_before = None
        self._modal_section_before = None
        if target == SELECT_SECTION_PLANE:
            plane = self._section_plane(section_plane_id)
            if plane is None:
                return CommandResult.failure("No section plane is active.", status="No section plane")
            if section_plane_id is None and (
                len(self.state.section_collection.selected_plane_ids) != 1
                or plane.id not in self.state.section_collection.selected_plane_ids
            ):
                return CommandResult.failure(
                    "Select one section plane to transform.",
                    status="Select one section plane to transform.",
                )
            section_origin = plane_origin(plane)
            section_normal = plane_normal(plane)
            section_axis = plane.axis
            section_offset = plane.offset
            self._modal_section_before = capture_section_workflow_state(self.state)
        else:
            self._modal_object_before = self._capture_object()

        mesh_object = self.state.mesh_object
        self.state.transform_state = ActiveTransformState(
            selected_item=target,
            mode=mode_key,
            mouse_start=start_position,
            axis_constraint=None,
            location=mesh_object.location.copy(),
            rotation=mesh_object.rotation.copy(),
            section_axis=section_axis,
            section_offset=section_offset,
            section_origin=section_origin,
            section_normal=section_normal,
            section_plane_id=None if plane is None else plane.id,
            section_plane_name=None if plane is None else plane.name,
        )
        self.state.active_transform_mode = mode_key
        self.state.active_transform_axis = self._display_axis(self.state.transform_state)
        self._last_readout = None
        self._angle_delta = 0.0 if mode_key == TRANSFORM_ROTATE else None
        self.events.publish(ActiveToolChangedEvent(tool_id=f"transform.{mode_key}"))
        publish_scene_change(
            self.events,
            reason="transform_started",
            changed_fields=(
                "transform_state",
                "active_transform_mode",
                "active_transform_axis",
            ),
        )
        return CommandResult.ok(
            status=self.active_status(),
            changed=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={"mode": mode_key, "selected_item": target},
        )

    def start_move(self, **kwargs: object) -> CommandResult:
        return self.start(TRANSFORM_MOVE, **kwargs)

    def start_rotate(self, **kwargs: object) -> CommandResult:
        return self.start(TRANSFORM_ROTATE, **kwargs)

    def set_axis_constraint(self, axis: str) -> CommandResult:
        axis_key = str(axis).strip().upper()
        session = self.state.transform_state
        if axis_key == "N":
            if (
                session is None
                or session.selected_item != SELECT_SECTION_PLANE
                or session.mode != TRANSFORM_MOVE
            ):
                return CommandResult.failure(
                    "Move Along Plane Normal is available while moving a section plane",
                    status="Move Along Plane Normal is available while moving a section plane",
                )
        elif axis_key not in {"X", "Y", "Z"}:
            return CommandResult.failure("Axis constraint must be X, Y, Z, or N.")

        if session is None:
            changed = self.state.active_transform_axis != axis_key
            self.state.active_transform_axis = axis_key
            if changed:
                publish_scene_change(
                    self.events,
                    reason="transform_axis_changed",
                    changed_fields=("active_transform_axis",),
                )
            return CommandResult.ok(
                status=f"Axis constraint: {axis_key}",
                changed=changed,
                ui_requests=MODEL_SYNC_UI_REQUESTS if changed else (),
                metadata={"axis": axis_key},
            )

        session.axis_constraint = None if session.axis_constraint == axis_key else axis_key
        self.state.active_transform_axis = self._display_axis(session)
        self._last_readout = None
        self._angle_delta = 0.0 if session.mode == TRANSFORM_ROTATE else None
        publish_scene_change(
            self.events,
            reason="transform_axis_changed",
            changed_fields=("transform_state", "active_transform_axis"),
        )
        return CommandResult.ok(
            status=self.active_status(),
            changed=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={"axis": session.axis_constraint},
        )

    def update(
        self,
        mouse_position: tuple[int, int],
        *,
        camera: CameraVectors | None = None,
        camera_right: object | None = None,
        camera_up: object | None = None,
        camera_forward: object | None = None,
        model_bounds: tuple[object, object] | None = None,
        fine: bool = False,
    ) -> CommandResult:
        session = self.state.transform_state
        if session is None:
            return CommandResult.failure("No transform is active.")
        try:
            position = (int(mouse_position[0]), int(mouse_position[1]))
            vectors = self._camera_vectors(
                camera,
                camera_right=camera_right,
                camera_up=camera_up,
                camera_forward=camera_forward,
            )
            diagonal = self._model_diagonal(model_bounds)
        except (IndexError, TypeError, ValueError) as exc:
            return CommandResult.failure(str(exc), status="Transform update failed")

        changed = False
        if session.selected_item == SELECT_MODEL:
            changed = self._update_model(session, position, vectors, diagonal, bool(fine))
        elif session.selected_item == SELECT_SECTION_PLANE:
            changed = self._update_section(session, position, vectors, diagonal, bool(fine))
        if not changed:
            return CommandResult.ok(status=self.active_status())
        publish_scene_change(
            self.events,
            reason="transform_preview_updated",
            changed_fields=(
                "mesh_object"
                if session.selected_item == SELECT_MODEL
                else "section_collection",
            ),
        )
        return CommandResult.ok(
            status=self.active_status(),
            changed=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={
                "readout": self._last_readout,
                "angle_delta": self._angle_delta,
                "axis": self._display_axis(session),
            },
        )

    update_active_transform = update

    def end(
        self,
        *,
        commit: bool,
        status: str | None = None,
    ) -> CommandResult:
        session = self.state.transform_state
        if session is None:
            return CommandResult.ok(status=status or "Transform")
        target = session.selected_item
        changed = self._session_changed(session)
        dependency_change: FeatureDependencyChange | None = None
        undo: CallbackUndoPayload | None = None
        reason = "transform_committed" if commit else "transform_cancelled"

        if not commit:
            self._restore_transform_start(session)
        elif changed and target == SELECT_MODEL:
            before = self._modal_object_before
            if before is not None:
                after = self._capture_object()
                undo = self._object_undo(
                    "Move Model" if session.mode == TRANSFORM_MOVE else "Rotate Model",
                    before,
                    after,
                )
        elif changed and target == SELECT_SECTION_PLANE:
            before_section = self._modal_section_before
            plane = self._section_plane(session.section_plane_id)
            if plane is not None:
                dependency_change = invalidate_section_plane_dependencies(
                    self.state,
                    plane.id,
                )
            if before_section is not None:
                after_section = capture_section_workflow_state(self.state)
                undo = self._section_undo(
                    "Move Section Plane"
                    if session.mode == TRANSFORM_MOVE
                    else "Rotate Section Plane",
                    before_section,
                    after_section,
                )

        previous_tool = f"transform.{session.mode}"
        self._clear_session()
        self.events.publish(
            ActiveToolChangedEvent(tool_id=None, previous_tool_id=previous_tool)
        )
        publish_scene_change(
            self.events,
            reason=reason,
            object_ids=(
                "model"
                if target == SELECT_MODEL
                else (session.section_plane_id or "section_plane"),
            ),
            changed_fields=(
                "transform_state",
                "active_transform_mode",
                "active_transform_axis",
                "mesh_object" if target == SELECT_MODEL else "section_collection",
            ),
        )
        result_status = status or ("Transform confirmed" if commit else "Transform cancelled")
        if commit and target == SELECT_MODEL:
            result_status = self._model_status(result_status)
        metadata: dict[str, object] = {
            "committed": bool(commit),
            "selected_item": target,
        }
        if dependency_change is not None:
            metadata.update(dependency_change.as_metadata())
        return CommandResult.ok(
            status=result_status,
            changed=changed,
            dirty=bool(commit and changed),
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo,
            metadata=metadata,
        )

    def commit(self, *, status: str = "Transform confirmed") -> CommandResult:
        return self.end(commit=True, status=status)

    def cancel(self, *, status: str = "Transform cancelled") -> CommandResult:
        return self.end(commit=False, status=status)

    def active_status(self) -> str:
        session = self.state.transform_state
        if session is None:
            return "No selection" if self.state.selected_item is None else "Transform"
        if session.selected_item == SELECT_SECTION_PLANE:
            return self._section_status(session)
        label = "Move mode" if session.mode == TRANSFORM_MOVE else "Rotate mode"
        axis = self._display_axis(session)
        parts = [label]
        if axis is not None:
            parts.append(f"{axis} axis")
        if self._last_readout is not None:
            parts.append(self._last_readout)
        elif session.mode == TRANSFORM_MOVE and axis is None:
            parts.append(
                "press X/Y/Z to constrain, Enter/Click to confirm, Esc/Right-click to cancel"
            )
        elif session.mode == TRANSFORM_ROTATE:
            parts.append("move mouse horizontally")
        return " - ".join(parts)

    def current_object_matrix(self) -> np.ndarray:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return np.identity(4)
        return build_object_transform_matrix(
            mesh_object.location,
            mesh_object.rotation,
            mesh_object.scale,
            mesh_object.origin,
        )

    def transformed_source_bounds(self) -> tuple[np.ndarray, np.ndarray]:
        mesh_object = self.state.mesh_object
        if (
            mesh_object is None
            or mesh_object.source_bounds_min is None
            or mesh_object.source_bounds_max is None
        ):
            zero = np.zeros(3, dtype=float)
            return (zero.copy(), zero.copy())
        return transform_bounds(
            mesh_object.source_bounds_min,
            mesh_object.source_bounds_max,
            self.current_object_matrix(),
        )

    def transformed_source_mesh(self) -> TriangleMeshData:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return TriangleMeshData(
                vertices=np.zeros((0, 3), dtype=float),
                triangles=np.zeros((0, 3), dtype=int),
            )
        mesh = mesh_object.source_mesh.copy()
        mesh.transform(self.current_object_matrix())
        return mesh

    def _change_origin(
        self,
        new_origin: object,
        *,
        status: str,
        reason: str,
    ) -> CommandResult:
        mesh_object = self.state.mesh_object
        assert mesh_object is not None
        next_origin = _vector3(new_origin, "Origin")
        if np.allclose(mesh_object.origin, next_origin, atol=1e-12):
            return CommandResult.ok(status=self._model_status(status))
        before = self._capture_object()
        old_origin = mesh_object.origin.copy()
        mesh_object.origin = next_origin
        mesh_object.location = calculate_location_for_origin_change(
            mesh_object.location,
            mesh_object.rotation,
            mesh_object.scale,
            old_origin,
            next_origin,
        )
        self._apply_object_transform()
        after = self._capture_object()
        return self._object_changed_result(
            status=self._model_status(status),
            reason=reason,
            undo=self._object_undo("Set Object Origin", before, after),
        )

    def _update_model(
        self,
        session: ActiveTransformState,
        position: tuple[int, int],
        camera: CameraVectors,
        diagonal: float,
        fine: bool,
    ) -> bool:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return False
        if session.mode == TRANSFORM_MOVE:
            if session.axis_constraint is None:
                movement, readout = camera_relative_move_delta(
                    session.mouse_start,
                    position,
                    camera.right,
                    camera.up,
                    diagonal,
                    fine=fine,
                )
            else:
                movement, amount = axis_constrained_camera_move_delta(
                    session.mouse_start,
                    position,
                    world_axis_vector(session.axis_constraint),
                    camera.right,
                    camera.up,
                    diagonal,
                    fine=fine,
                )
                readout = f"Delta {session.axis_constraint}: {amount:.2f}"
            next_location = session.location + movement
            changed = not np.allclose(mesh_object.location, next_location, atol=1e-12)
            mesh_object.location = next_location
            self._last_readout = readout
            self._angle_delta = None
        else:
            axis = self._display_axis(session) or "Z"
            next_rotation, angle = mesh_rotate_delta(
                session.mouse_start,
                position,
                session.rotation,
                axis,
                fine=fine,
            )
            changed = not np.allclose(mesh_object.rotation, next_rotation, atol=1e-12)
            mesh_object.rotation = next_rotation
            self.state.active_transform_axis = axis
            self._last_readout = f"{angle:.1f} deg"
            self._angle_delta = angle
        self._apply_object_transform()
        return changed

    def _update_section(
        self,
        session: ActiveTransformState,
        position: tuple[int, int],
        camera: CameraVectors,
        diagonal: float,
        fine: bool,
    ) -> bool:
        plane = self._section_plane(session.section_plane_id)
        if plane is None:
            return False
        old_origin = plane_origin(plane)
        old_normal = plane_normal(plane)
        if session.mode == TRANSFORM_MOVE:
            if session.axis_constraint is None:
                movement, _readout = camera_relative_move_delta(
                    session.mouse_start,
                    position,
                    camera.right,
                    camera.up,
                    diagonal,
                    fine=fine,
                )
                readout = _section_movement_readout(movement)
            elif session.axis_constraint == "N":
                movement, amount = axis_constrained_camera_move_delta(
                    session.mouse_start,
                    position,
                    session.section_normal,
                    camera.right,
                    camera.up,
                    diagonal,
                    fine=fine,
                )
                readout = f"{amount:.3f}"
            else:
                movement, amount = axis_constrained_camera_move_delta(
                    session.mouse_start,
                    position,
                    world_axis_vector(session.axis_constraint),
                    camera.right,
                    camera.up,
                    diagonal,
                    fine=fine,
                )
                readout = f"Delta {session.axis_constraint} {amount:.3f}"
            set_plane_origin_normal(
                plane,
                session.section_origin + movement,
                session.section_normal,
            )
            self._last_readout = readout
            self._angle_delta = None
        else:
            axis = self._display_axis(session)
            _rotation, angle = mesh_rotate_delta(
                session.mouse_start,
                position,
                np.zeros(3, dtype=float),
                axis or "Z",
                fine=fine,
            )
            rotation_axis = (
                world_axis_vector(axis)
                if axis in {"X", "Y", "Z"}
                else self._section_view_rotation_axis(session, camera)
            )
            normal = rotate_vector_around_axis(
                session.section_normal,
                rotation_axis,
                angle,
            )
            set_plane_origin_normal(plane, session.section_origin, normal)
            self.state.active_transform_axis = axis
            self._last_readout = f"{angle:.1f} deg"
            self._angle_delta = angle
        return not (
            np.allclose(old_origin, plane_origin(plane), atol=1e-12)
            and np.allclose(old_normal, plane_normal(plane), atol=1e-12)
        )

    def _restore_transform_start(self, session: ActiveTransformState) -> None:
        if session.selected_item == SELECT_MODEL:
            if self._modal_object_before is not None:
                self._restore_object(self.state, self._modal_object_before)
            return
        plane = self._section_plane(session.section_plane_id)
        if plane is None:
            return
        plane.axis = session.section_axis
        set_plane_origin_normal(
            plane,
            session.section_origin.copy(),
            session.section_normal.copy(),
        )
        plane.offset = float(session.section_offset)
        normalize_plane_state(plane)

    def _session_changed(self, session: ActiveTransformState) -> bool:
        if session.selected_item == SELECT_MODEL:
            mesh_object = self.state.mesh_object
            if mesh_object is None:
                return False
            return not (
                np.allclose(mesh_object.location, session.location, atol=1e-8)
                and np.allclose(mesh_object.rotation, session.rotation, atol=1e-8)
            )
        plane = self._section_plane(session.section_plane_id)
        if plane is None:
            return False
        return not (
            np.allclose(plane_origin(plane), session.section_origin, atol=1e-8)
            and np.allclose(plane_normal(plane), session.section_normal, atol=1e-8)
        )

    def _capture_object(self, *, include_geometry: bool = False) -> ObjectTransformSnapshot:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            raise ValueError("No mesh is loaded.")
        return ObjectTransformSnapshot(
            origin=mesh_object.origin.copy(),
            location=mesh_object.location.copy(),
            rotation=mesh_object.rotation.copy(),
            scale=float(mesh_object.scale),
            transform_matrix=(
                None
                if mesh_object.transform_matrix is None
                else np.asarray(mesh_object.transform_matrix, dtype=float).copy()
            ),
            source_bounds_min=_copy_array(mesh_object.source_bounds_min),
            source_bounds_max=_copy_array(mesh_object.source_bounds_max),
            source_vertices=(
                mesh_object.source_mesh.vertices.copy() if include_geometry else None
            ),
            display_vertices=(
                mesh_object.display_mesh.vertices.copy() if include_geometry else None
            ),
        )

    def _restore_object(
        self,
        target_state: AppState,
        snapshot: ObjectTransformSnapshot,
    ) -> None:
        mesh_object = target_state.mesh_object
        if mesh_object is None:
            return
        mesh_object.origin = snapshot.origin.copy()
        mesh_object.location = snapshot.location.copy()
        mesh_object.rotation = snapshot.rotation.copy()
        mesh_object.scale = float(snapshot.scale)
        mesh_object.transform_matrix = _copy_array(snapshot.transform_matrix)
        mesh_object.source_bounds_min = _copy_array(snapshot.source_bounds_min)
        mesh_object.source_bounds_max = _copy_array(snapshot.source_bounds_max)
        if snapshot.source_vertices is not None:
            mesh_object.source_mesh.vertices = snapshot.source_vertices.copy()
        if snapshot.display_vertices is not None:
            mesh_object.display_mesh.vertices = snapshot.display_vertices.copy()
        self._invalidate_mesh_query()

    def _object_undo(
        self,
        name: str,
        before: ObjectTransformSnapshot,
        after: ObjectTransformSnapshot,
    ) -> CallbackUndoPayload:
        target_state = self.state

        def restore(snapshot: ObjectTransformSnapshot, reason: str) -> None:
            self._restore_object(target_state, snapshot)
            publish_scene_change(
                self.events,
                reason=reason,
                object_ids=("model",),
                changed_fields=("mesh_object",),
            )

        return CallbackUndoPayload(
            name=name,
            undo_action=lambda: restore(before, "object_transform_undo"),
            redo_action=lambda: restore(after, "object_transform_redo"),
        )

    def _section_undo(
        self,
        name: str,
        before: SectionWorkflowSnapshot,
        after: SectionWorkflowSnapshot,
    ) -> CallbackUndoPayload:
        target_state = self.state

        def restore(snapshot: SectionWorkflowSnapshot, reason: str) -> None:
            restore_section_workflow_state(target_state, snapshot)
            publish_scene_change(
                self.events,
                reason=reason,
                changed_fields=(
                    "section_collection",
                    "curve_collection",
                    "surface_collection",
                    "brep_surface_collection",
                ),
            )

        return CallbackUndoPayload(
            name=name,
            undo_action=lambda: restore(before, "section_transform_undo"),
            redo_action=lambda: restore(after, "section_transform_redo"),
        )

    def _object_changed_result(
        self,
        *,
        status: str,
        reason: str,
        undo: CallbackUndoPayload,
    ) -> CommandResult:
        publish_scene_change(
            self.events,
            reason=reason,
            object_ids=("model",),
            changed_fields=("mesh_object",),
        )
        return CommandResult.ok(
            status=status,
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo,
            metadata={"transform_matrix": self.current_object_matrix().copy()},
        )

    def _apply_object_transform(self) -> None:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return
        mesh_object.transform_matrix = self.current_object_matrix()
        self._invalidate_mesh_query()

    def _invalidate_mesh_query(self) -> None:
        if self._mesh_query_invalidator is not None:
            self._mesh_query_invalidator()

    def _section_plane(self, plane_id: str | None) -> SectionPlaneState | None:
        if plane_id is None:
            return get_active_plane(self.state.section_collection)
        return next(
            (
                plane
                for plane in self.state.section_collection.planes
                if plane.id == str(plane_id)
            ),
            None,
        )

    def _model_diagonal(self, bounds: tuple[object, object] | None) -> float:
        if bounds is None:
            minimum, maximum = self.transformed_source_bounds()
        else:
            minimum = _vector3(bounds[0], "Minimum bound")
            maximum = _vector3(bounds[1], "Maximum bound")
        return float(np.linalg.norm(maximum - minimum))

    @staticmethod
    def _camera_vectors(
        camera: CameraVectors | None,
        *,
        camera_right: object | None,
        camera_up: object | None,
        camera_forward: object | None,
    ) -> CameraVectors:
        if camera is not None:
            if not isinstance(camera, CameraVectors):
                raise TypeError("camera must be CameraVectors.")
            return camera
        if camera_right is None or camera_up is None:
            raise ValueError("Camera right and up vectors are required.")
        forward = (
            np.cross(_vector3(camera_right, "camera right"), _vector3(camera_up, "camera up"))
            if camera_forward is None
            else camera_forward
        )
        return CameraVectors(camera_right, camera_up, forward)

    @staticmethod
    def _display_axis(session: ActiveTransformState) -> str | None:
        if session.mode == TRANSFORM_ROTATE and session.selected_item == SELECT_MODEL:
            return session.axis_constraint or "Z"
        return session.axis_constraint

    @staticmethod
    def _section_view_rotation_axis(
        session: ActiveTransformState,
        camera: CameraVectors,
    ) -> np.ndarray:
        section_normal = normalized_vector(
            session.section_normal,
            fallback=np.asarray([0.0, 0.0, 1.0], dtype=float),
        )
        for candidate in (camera.up, camera.right, camera.forward):
            candidate_axis = normalized_vector(
                np.asarray(candidate, dtype=float),
                fallback=np.asarray([1.0, 0.0, 0.0], dtype=float),
            )
            if abs(float(np.dot(candidate_axis, section_normal))) < 0.92:
                return candidate_axis
        return world_axis_vector("X")

    def _section_status(self, session: ActiveTransformState) -> str:
        name = session.section_plane_name or "Section Plane"
        axis = self._display_axis(session)
        if session.mode == TRANSFORM_MOVE:
            if self._last_readout is None:
                if axis == "N":
                    return f"Moving {name} along normal: drag mouse"
                if axis in {"X", "Y", "Z"}:
                    return f"Moving {name} along {axis}: drag mouse"
                return (
                    f"Moving {name}: camera-relative grab "
                    "(X/Y/Z constrain, N normal, Enter/click confirm, Esc cancel)"
                )
            if axis == "N":
                return f"Moving {name} along normal: {self._last_readout}"
            return f"Moving {name}: {self._last_readout}"
        label = axis if axis in {"X", "Y", "Z"} else "view"
        if self._last_readout is None:
            return f"Rotating {name} around {label}: move mouse horizontally"
        return f"Rotating {name} around {label}: {self._last_readout}"

    def _clear_session(self) -> None:
        self.state.transform_state = None
        self.state.active_transform_mode = None
        self.state.active_transform_axis = None
        self._last_readout = None
        self._angle_delta = None
        self._modal_object_before = None
        self._modal_section_before = None

    def _has_generated_geometry(self) -> bool:
        return bool(
            self.state.section_collection.results
            or self.state.curve_collection.curves
            or self.state.surface_collection.surfaces
            or self.state.brep_surface_collection.surfaces
        )

    def _model_status(self, default: str) -> str:
        return GENERATED_GEOMETRY_TRANSFORM_WARNING if self._has_generated_geometry() else default


def _vector3(value: object, label: str) -> np.ndarray:
    try:
        values = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain three numbers.") from exc
    if values.shape != (3,) or not np.all(np.isfinite(values)):
        raise ValueError(f"{label} must contain three finite numbers.")
    return values.copy()


def _positive_number(value: object, label: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a number.") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite.")
    if number <= 0.0:
        raise ValueError(f"{label} must be greater than zero.")
    return number


def _copy_array(value: object | None) -> np.ndarray | None:
    return None if value is None else np.asarray(value, dtype=float).copy()


def _section_movement_readout(movement: np.ndarray) -> str:
    values = np.asarray(movement, dtype=float)
    return (
        f"Delta X {values[0]:.3f}, "
        f"Delta Y {values[1]:.3f}, "
        f"Delta Z {values[2]:.3f}"
    )


__all__ = (
    "CameraVectors",
    "GENERATED_GEOMETRY_TRANSFORM_WARNING",
    "ObjectTransformSnapshot",
    "TransformController",
)
