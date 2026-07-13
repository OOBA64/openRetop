"""UI-independent controller for drawing and editing manual curves."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

from curves.curve_state import (
    CurveProcessingError,
    StoredCurve,
    refresh_curve_diagnostics,
    simplify_curve,
)
from curves.manual_curve import (
    CURVE_POINT_CORNER,
    CURVE_POINT_SMOOTH,
    CURVE_POINT_SOURCE_AUTO,
    CURVE_POINT_SOURCE_MANUAL,
    DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
    DEFAULT_MANUAL_CURVE_METHOD,
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    DEFAULT_MANUAL_CURVE_SMOOTHNESS,
    MANUAL_CURVE_METHOD_POLYLINE,
    MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
    ManualCurveControlDataV2,
    ManualCurvePoint,
    auto_detect_manual_curve_corners,
    build_manual_stored_curve,
    clear_auto_detected_manual_curve_corners,
    parse_manual_curve_metadata_v2,
    sample_hybrid_manual_curve,
    should_snap_closed_to_first_point,
    simplify_manual_curve_control_data,
    is_manual_curve_like,
)
from curves.manual_curve_session import ManualCurveSessionState
from curves.projection import project_curve_points_to_mesh
from mesh.query_service import MeshQueryService
from mesh.triangle_mesh import TriangleMeshData


@dataclass(frozen=True)
class ManualCurveActionResult:
    success: bool = True
    changed: bool = False
    status: str = ""
    needs_viewport_refresh: bool = False
    needs_ui_sync: bool = True
    project_dirty: bool = False
    created_curve: StoredCurve | None = None
    updated_curve: StoredCurve | None = None
    completed_curve_id: str | None = None
    warnings: tuple[str, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class ManualCurveInputResult:
    action: str = "none"
    consumed: bool = False
    control_point_index: int | None = None
    status: str = ""


@dataclass(frozen=True)
class ManualCurveDisplayState:
    active: bool
    editing: bool
    control_points: Sequence[np.ndarray] | None
    point_types: Sequence[str] | None
    fitted_points: np.ndarray | None
    is_closed: bool
    plane_normal: np.ndarray | None
    snap_to_mesh: bool
    selected_point_index: int | None
    curve_method: str
    sample_count: int
    preview_point: np.ndarray | None
    preview_valid: bool
    preview_snaps_closed: bool
    preview_snaps_to_mesh: bool


class ManualCurveController:
    """Own manual-curve workflow behavior while remaining independent of the UI."""

    def __init__(
        self,
        *,
        session: ManualCurveSessionState | None = None,
        mesh_query_service: MeshQueryService | None = None,
    ) -> None:
        self.session = session or ManualCurveSessionState()
        self.mesh_query_service = mesh_query_service
        self._display_cache_key: object | None = None
        self._display_fitted_points: np.ndarray | None = None

    def begin_new_curve(
        self,
        *,
        plane_origin: object,
        plane_normal: object,
        plane_type: str = "world_xy",
        plane_label: str = "world XY plane",
        source_section_plane_id: str | None = None,
        snap_to_mesh: bool = False,
        keep_curve_on_mesh: bool = False,
        curve_method: str = DEFAULT_MANUAL_CURVE_METHOD,
        sample_count: int = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
        smoothness: int = DEFAULT_MANUAL_CURVE_SMOOTHNESS,
        preserve_corners: bool = True,
        corner_angle_threshold_degrees: float = DEFAULT_CORNER_ANGLE_THRESHOLD_DEGREES,
        auto_detect_corners: bool = False,
    ) -> ManualCurveActionResult:
        self.session.begin_new_curve(
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            plane_type=plane_type,
            plane_label=plane_label,
            source_section_plane_id=source_section_plane_id,
            snap_to_mesh=snap_to_mesh,
            keep_curve_on_mesh=keep_curve_on_mesh,
            curve_method=curve_method,
            sample_count=sample_count,
            smoothness=smoothness,
            preserve_corners=preserve_corners,
            corner_angle_threshold_degrees=corner_angle_threshold_degrees,
            auto_detect_corners=auto_detect_corners,
        )
        self.invalidate_display_cache()
        return self._result(
            changed=True,
            status=self.status(),
            refresh=True,
        )

    def begin_edit_curve(
        self,
        curve: StoredCurve,
        *,
        plane_origin: object = (0.0, 0.0, 0.0),
        plane_normal: object = (0.0, 0.0, 1.0),
        plane_type: str = "world_xy",
        plane_label: str = "world XY plane",
        source_section_plane_id: str | None = None,
    ) -> ManualCurveActionResult:
        control_data = self.control_data_for_curve(curve)
        if control_data is None:
            return self._result(
                success=False,
                status="Selected curve has no editable control points.",
            )
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        self.session.begin_edit_curve(
            control_data,
            curve_id=curve.id,
            metadata=metadata,
            plane_origin=plane_origin,
            plane_normal=plane_normal,
            plane_type=plane_type,
            plane_label=plane_label,
            source_section_plane_id=source_section_plane_id,
        )
        self.invalidate_display_cache()
        return self._result(
            changed=True,
            status="Editing curve: select or drag control points. Right-drag to orbit.",
            refresh=True,
        )

    def start_new_curve(self, **kwargs: object) -> ManualCurveActionResult:
        return self.begin_new_curve(**kwargs)

    def load_curve_for_editing(
        self,
        curve: StoredCurve,
        **kwargs: object,
    ) -> ManualCurveActionResult:
        return self.begin_edit_curve(curve, **kwargs)

    @staticmethod
    def control_data_for_curve(curve: StoredCurve) -> ManualCurveControlDataV2 | None:
        control_data = parse_manual_curve_metadata_v2(curve)
        if control_data is not None:
            return control_data
        points = _finite_points(curve.original_points)
        if points is None:
            points = _finite_points(curve.fitted_points)
        if points is None:
            return None
        return ManualCurveControlDataV2(
            points=[ManualCurvePoint(position=point) for point in points],
            is_closed=bool(curve.is_closed),
            curve_method=MANUAL_CURVE_METHOD_POLYLINE,
            sample_count=DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
        )

    @staticmethod
    def is_editable_curve(curve: StoredCurve) -> bool:
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        creation_type = str(metadata.get("creation_type", "")).strip().lower()
        return bool(
            creation_type
            in {
                "manual",
                "curve_on_mesh",
                "region_boundary",
                "hybrid_region_guide",
                "projected_curve",
                "rebuilt_curve",
            }
            or "control_points" in metadata
            or is_manual_curve_like(curve)
        )

    def exit(self) -> ManualCurveActionResult:
        completed_id = self.session.edit_curve_id
        changed = self.session.active
        self.session.exit()
        self.invalidate_display_cache()
        return self._result(
            changed=changed,
            status="Manual curve editing finished",
            refresh=changed,
            completed_curve_id=completed_id,
        )

    def cancel(self, *, status: str = "Manual curve cancelled") -> ManualCurveActionResult:
        result = self.exit()
        return ManualCurveActionResult(
            success=True,
            changed=result.changed,
            status=status,
            needs_viewport_refresh=result.needs_viewport_refresh,
            needs_ui_sync=True,
            completed_curve_id=result.completed_curve_id,
        )

    def cancel_workflow(
        self,
        *,
        status: str = "Manual curve cancelled",
    ) -> ManualCurveActionResult:
        return self.cancel(status=status)

    def configure(
        self,
        *,
        curve_method: str | None = None,
        sample_count: int | None = None,
        smoothness: int | None = None,
        preserve_corners: bool | None = None,
        corner_angle_threshold_degrees: float | None = None,
        auto_detect_corners: bool | None = None,
        snap_to_mesh: bool | None = None,
        keep_curve_on_mesh: bool | None = None,
    ) -> ManualCurveActionResult:
        session = self.session
        before = self._display_option_key()
        previous_threshold = session.corner_angle_threshold_degrees
        previous_auto_detect = session.auto_detect_corners
        if curve_method is not None:
            session.curve_method = str(curve_method)
        if sample_count is not None:
            session.sample_count = min(max(int(sample_count), 16), 2048)
        if smoothness is not None:
            session.smoothness = min(max(int(smoothness), 1), 8)
        if preserve_corners is not None:
            session.preserve_corners = bool(preserve_corners)
        if corner_angle_threshold_degrees is not None:
            session.corner_angle_threshold_degrees = min(
                max(float(corner_angle_threshold_degrees), 1.0), 179.0
            )
        if auto_detect_corners is not None:
            session.auto_detect_corners = bool(auto_detect_corners)
        if snap_to_mesh is not None:
            session.snap_to_mesh = bool(snap_to_mesh)
        if keep_curve_on_mesh is not None:
            session.keep_curve_on_mesh = bool(keep_curve_on_mesh)
            if session.keep_curve_on_mesh:
                session.snap_to_mesh = True
        changed = before != self._display_option_key()
        if changed:
            self.invalidate_display_cache()
        if (
            session.active
            and session.auto_detect_corners
            and len(session.control_points) >= 3
            and (
                session.corner_angle_threshold_degrees != previous_threshold
                or (session.auto_detect_corners and not previous_auto_detect)
            )
        ):
            return self.auto_detect_corners(set_status=False)
        return self._result(changed=changed, refresh=changed and session.active)

    def set_work_plane(
        self,
        *,
        plane_origin: object,
        plane_normal: object,
        plane_type: str,
        plane_label: str,
        source_section_plane_id: str | None = None,
    ) -> ManualCurveActionResult:
        session = self.session
        before = (
            tuple(float(value) for value in session.plane_origin),
            tuple(float(value) for value in session.plane_normal),
            session.plane_type,
            session.plane_label,
            session.source_section_plane_id,
        )
        session._set_plane(
            plane_origin,
            plane_normal,
            plane_type=plane_type,
            plane_label=plane_label,
            source_section_plane_id=source_section_plane_id,
        )
        after = (
            tuple(float(value) for value in session.plane_origin),
            tuple(float(value) for value in session.plane_normal),
            session.plane_type,
            session.plane_label,
            session.source_section_plane_id,
        )
        return self._result(changed=before != after, refresh=False)

    def append_point(
        self,
        point: object,
        *,
        point_type: str = CURVE_POINT_SMOOTH,
        snapped: bool = False,
        triangle_index: int | None = None,
        normal: object | None = None,
        projection_distance: float | None = None,
    ) -> ManualCurveActionResult:
        source = (
            CURVE_POINT_SOURCE_MANUAL
            if point_type == CURVE_POINT_CORNER
            else CURVE_POINT_SOURCE_AUTO
        )
        index = self.session.append_point(
            point,
            point_type=point_type,
            point_type_source=source,
            snapped=snapped,
            triangle_index=triangle_index,
            normal=normal,
            projection_distance=projection_distance,
        )
        self._auto_detect_after_append()
        self.invalidate_display_cache()
        return self._result(
            changed=True,
            status=self.status(),
            refresh=True,
            metadata={"control_point_index": index},
        )

    def insert_point(
        self,
        index: int,
        point: object,
        *,
        point_type: str = CURVE_POINT_SMOOTH,
        snapped: bool = False,
        triangle_index: int | None = None,
        normal: object | None = None,
        projection_distance: float | None = None,
    ) -> ManualCurveActionResult:
        source = (
            CURVE_POINT_SOURCE_MANUAL
            if point_type == CURVE_POINT_CORNER
            else CURVE_POINT_SOURCE_AUTO
        )
        insert_index = self.session.insert_point(
            index,
            point,
            point_type=point_type,
            point_type_source=source,
            snapped=snapped,
            triangle_index=triangle_index,
            normal=normal,
            projection_distance=projection_distance,
        )
        self.session.select_point(insert_index)
        self._auto_detect_all_if_enabled()
        self.invalidate_display_cache()
        return self._result(
            changed=True,
            status="Point inserted. Insert mode off.",
            refresh=True,
            metadata={"control_point_index": insert_index},
        )

    def move_point(
        self,
        index: int,
        point: object,
        *,
        snapped: bool | None = None,
        triangle_index: int | None = None,
        normal: object | None = None,
        projection_distance: float | None = None,
    ) -> ManualCurveActionResult:
        self.session.move_point(
            index,
            point,
            snapped=snapped,
            triangle_index=triangle_index,
            normal=normal,
            projection_distance=projection_distance,
        )
        self._auto_detect_all_if_enabled()
        self.invalidate_display_cache()
        return self._result(changed=True, status=self.status(), refresh=True)

    def move_drag_candidate(
        self,
        point: object,
        *,
        snapped: bool | None = None,
        triangle_index: int | None = None,
        normal: object | None = None,
        projection_distance: float | None = None,
    ) -> ManualCurveActionResult:
        index = self.session.drag_candidate_index
        if index is None:
            return self._result(success=False)
        self.session.move_point(
            index,
            point,
            snapped=snapped,
            triangle_index=triangle_index,
            normal=normal,
            projection_distance=projection_distance,
            mark_controls_changed=False,
        )
        self.session.drag_active = True
        self.invalidate_display_cache()
        return self._result(changed=True, status=self.status(), refresh=True)

    def remove_last_point(self) -> ManualCurveActionResult:
        if not self.session.control_points:
            return self._result(
                success=False,
                status="Manual Curve: no pending points",
            )
        self.session.remove_point(len(self.session.control_points) - 1)
        self._auto_detect_all_if_enabled()
        self.invalidate_display_cache()
        return self._result(changed=True, status=self.status(), refresh=True)

    def delete_selected_point(self) -> ManualCurveActionResult:
        session = self.session
        index = session.selected_control_point_index
        if not session.editing:
            return self._result(
                success=False,
                status="Edit a manual curve before deleting control points.",
            )
        if index is None:
            return self._result(success=False, status="No control point selected")
        minimum = 3 if session.is_closed else 2
        if len(session.control_points) <= minimum:
            return self._result(
                success=False,
                status="Cannot delete point: curve needs more control points",
            )
        session.remove_point(index)
        self._auto_detect_all_if_enabled()
        self.invalidate_display_cache()
        selected = session.selected_control_point_index
        return self._result(
            changed=True,
            status=f"Deleted control point {(selected or 0) + 1}",
            refresh=True,
        )

    def select_point(self, index: int | None) -> ManualCurveActionResult:
        selected = self.session.select_point(index)
        self.session.drag_candidate_index = None
        self.session.submode = "edit_select" if self.session.editing else self.session.submode
        status = (
            "No control point selected"
            if selected is None
            else f"Selected control point {selected + 1}: {self.session.point_types[selected]}"
        )
        return self._result(
            changed=True,
            status=status,
            refresh=True,
            metadata={"control_point_index": selected},
        )

    def set_selected_point_type(self, point_type: str) -> ManualCurveActionResult:
        index = self.session.selected_control_point_index
        if index is None or not 0 <= index < len(self.session.control_points):
            return self._result(success=False, status="No control point selected")
        self.session.normalize_parallel_arrays()
        self.session.point_types[index] = (
            CURVE_POINT_CORNER
            if str(point_type).strip().lower() == CURVE_POINT_CORNER
            else CURVE_POINT_SMOOTH
        )
        self.session.point_type_sources[index] = CURVE_POINT_SOURCE_MANUAL
        self.invalidate_display_cache()
        return self._result(
            changed=True,
            status=f"Control point {index + 1}: {self.session.point_types[index]}",
            refresh=True,
        )

    def auto_detect_corners(
        self,
        *,
        set_status: bool = True,
    ) -> ManualCurveActionResult:
        if len(self.session.control_points) < 3:
            return self._result(
                success=False,
                status="Corner detection requires at least 3 points." if set_status else "",
            )
        detected = auto_detect_manual_curve_corners(
            self.session.to_control_data_v2(),
            threshold_degrees=self.session.corner_angle_threshold_degrees,
        )
        self._load_corner_classification(detected)
        self.invalidate_display_cache()
        count = sum(value == CURVE_POINT_CORNER for value in self.session.point_types)
        return self._result(
            changed=True,
            status=f"Detected {count} corner points." if set_status else "",
            refresh=True,
        )

    def clear_auto_corners(self) -> ManualCurveActionResult:
        if not self.session.active:
            return self._result(
                success=False,
                status="Edit a manual curve before clearing auto corners.",
            )
        cleared = clear_auto_detected_manual_curve_corners(
            self.session.to_control_data_v2()
        )
        self._load_corner_classification(cleared)
        self.invalidate_display_cache()
        return self._result(
            changed=True,
            status="Cleared auto-detected corners; manual corners preserved.",
            refresh=True,
        )

    def toggle_closed(self) -> ManualCurveActionResult:
        return self.set_closed(not self.session.is_closed)

    def set_closed(self, closed: bool) -> ManualCurveActionResult:
        if bool(closed) and len(self.session.control_points) < 3:
            return self._result(
                success=False,
                status="Manual Curve: need at least 3 points to close",
            )
        value = bool(closed)
        changed = self.session.is_closed != value
        self.session.set_closed(value)
        self._auto_detect_all_if_enabled()
        self.invalidate_display_cache()
        status = (
            ("Curve closed" if value else "Curve opened")
            if self.session.editing
            else self.status()
        )
        return self._result(changed=changed, status=status, refresh=changed)

    def snap_closed(self, *, edit_status: bool = False) -> ManualCurveActionResult:
        if len(self.session.control_points) < 3:
            return self._result(success=False)
        changed = not self.session.is_closed
        if changed:
            self.session.set_closed(True)
            self._auto_detect_all_if_enabled()
            self.invalidate_display_cache()
        self.session.selected_control_point_index = 0 if edit_status else None
        self.session.clear_preview()
        return self._result(
            changed=changed,
            status="Curve closed to first point" if changed else "Manual Curve: already closed",
            refresh=True,
        )

    def should_snap_closed(
        self,
        point: object,
        *,
        model_extent: float | None = None,
    ) -> bool:
        return should_snap_closed_to_first_point(
            self.session.control_points,
            point,
            model_extent=model_extent,
        )

    def activate_add_point(self) -> ManualCurveActionResult:
        if not self.session.active:
            return self._result(
                success=False,
                status="Create or edit a manual curve before adding points.",
            )
        self.session.add_point_active = True
        self.session.insert_point_active = False
        self.session.placing_enabled = True
        self.session.submode = "explicit_add_point"
        return self._result(
            changed=True,
            status="Add Point active: left-click to append. Esc returns to edit mode.",
        )

    def activate_insert_point(self) -> ManualCurveActionResult:
        if not self.session.editing:
            return self._result(
                success=False,
                status="Edit a manual curve before inserting points.",
            )
        self.session.insert_point_active = True
        self.session.add_point_active = False
        self.session.placing_enabled = True
        self.session.submode = "explicit_insert_point"
        return self._result(
            changed=True,
            status="Insert Point active: click a curve segment. Esc returns to edit mode.",
        )

    def complete_explicit_point_action(self) -> None:
        self.session.add_point_active = False
        self.session.insert_point_active = False
        self.session.placing_enabled = False
        self.session.submode = "edit_select" if self.session.editing else "inactive"
        self.session.clear_preview()

    def cancel_subaction(self, *, status: str) -> ManualCurveActionResult:
        session = self.session
        if (
            session.drag_active
            or session.drag_candidate_index is not None
            or session.submode == "edit_move_point"
        ):
            session.drag_active = False
            session.drag_candidate_index = None
            session.left_press_position = None
            session.left_dragged = False
            session.submode = "edit_select"
            session.clear_preview()
            return self._result(changed=True, status=status)
        if (
            not session.editing
            and session.submode == "draw_add_points"
            and session.placing_enabled
        ):
            session.add_point_active = False
            session.insert_point_active = False
            session.placing_enabled = False
            session.submode = "inactive"
            session.clear_preview()
            return self._result(changed=True, status=status, refresh=True)
        if session.add_point_active or session.insert_point_active:
            self.complete_explicit_point_action()
            return self._result(changed=True, status=status)
        return self._result(success=False)

    def handle_escape(self) -> ManualCurveActionResult:
        status = (
            "Manual Curve: action cancelled"
            if self.session.editing
            else "Point placement paused. Press Add Point to continue."
        )
        subaction = self.cancel_subaction(status=status)
        if subaction.success:
            return ManualCurveActionResult(
                **{
                    **subaction.__dict__,
                    "metadata": {"exited_submode": True},
                }
            )
        completed_id = self.session.edit_curve_id
        was_editing = self.session.editing
        self.session.exit()
        self.invalidate_display_cache()
        return self._result(
            changed=True,
            status=(
                "Manual curve editing finished"
                if was_editing
                else "Manual curve cancelled"
            ),
            refresh=True,
            completed_curve_id=completed_id,
            metadata={"exited_workflow": True},
        )

    def resume_add_points(self) -> ManualCurveActionResult:
        if not self.session.active or self.session.editing:
            return self.activate_add_point()
        self.session.placing_enabled = True
        self.session.submode = "draw_add_points"
        return self._result(changed=True, status=self.status())

    def route_pointer_event(
        self,
        event_type: str,
        *,
        button: str | None = None,
        control_point_index: int | None = None,
        dragged: bool = False,
        press_position: tuple[int, int] | None = None,
    ) -> ManualCurveInputResult:
        """Decide the workflow action after screen-space resolution by an adapter."""

        event = str(event_type).strip().lower()
        button_name = str(button or "").strip().lower()
        if button_name in {"right", "middle", "wheel"} or event in {
            "right_press",
            "right_release",
            "middle_press",
            "middle_release",
            "wheel",
        }:
            return ManualCurveInputResult(consumed=False)
        if not self.session.active:
            return ManualCurveInputResult(consumed=False)
        if event == "leave":
            self.session.clear_preview()
            return ManualCurveInputResult(action="clear_preview", consumed=True)
        if event in {"press", "left_press"}:
            self.session.left_press_position = press_position
            self.session.left_dragged = False
            self.session.drag_candidate_index = None
            if (
                self.session.editing
                and not self.session.add_point_active
                and not self.session.insert_point_active
                and control_point_index is not None
            ):
                selected = self.session.select_point(control_point_index)
                self.session.drag_candidate_index = selected
                self.session.submode = "edit_move_point"
                return ManualCurveInputResult(
                    action="begin_drag",
                    consumed=True,
                    control_point_index=selected,
                )
            return ManualCurveInputResult(action="none", consumed=True)
        if event == "motion":
            if self.session.drag_candidate_index is not None and dragged:
                self.session.left_dragged = True
                return ManualCurveInputResult(
                    action="move_point",
                    consumed=True,
                    control_point_index=self.session.drag_candidate_index,
                )
            return ManualCurveInputResult(action="preview", consumed=True)
        if event in {"release", "left_release"}:
            if self.session.drag_active:
                index = self.session.drag_candidate_index
                self.finish_drag()
                return ManualCurveInputResult(
                    action="finish_drag",
                    consumed=True,
                    control_point_index=index,
                )
            if self.session.left_dragged:
                self.finish_drag()
                return ManualCurveInputResult(action="none", consumed=True)
            if self.session.editing:
                if self.session.add_point_active:
                    return ManualCurveInputResult(action="add_point", consumed=True)
                if self.session.insert_point_active:
                    return ManualCurveInputResult(action="insert_point", consumed=True)
                return ManualCurveInputResult(
                    action="select_point",
                    consumed=True,
                    control_point_index=control_point_index,
                )
            if self.session.placing_enabled:
                return ManualCurveInputResult(action="add_point", consumed=True)
            return ManualCurveInputResult(action="none", consumed=True)
        return ManualCurveInputResult(consumed=False)

    def finish_drag(self) -> ManualCurveActionResult:
        controls_changed = self.session.drag_active
        self.session.drag_active = False
        self.session.drag_candidate_index = None
        self.session.left_press_position = None
        self.session.left_dragged = False
        self.session.submode = "edit_select" if self.session.editing else "draw_add_points"
        if controls_changed:
            self.session.mark_controls_changed()
            self._auto_detect_all_if_enabled()
            self.invalidate_display_cache()
        return self._result(
            changed=controls_changed,
            refresh=controls_changed,
        )

    def handle_pointer_event(
        self,
        event_type: str,
        **kwargs: object,
    ) -> ManualCurveInputResult:
        return self.route_pointer_event(event_type, **kwargs)

    def update_drag_state(self, x_position: int, y_position: int) -> bool:
        start = self.session.left_press_position
        if start is None:
            return self.session.left_dragged
        distance = abs(int(x_position) - start[0]) + abs(int(y_position) - start[1])
        if distance > 4:
            self.session.left_dragged = True
        return self.session.left_dragged

    def should_drag_selected_point(self) -> bool:
        session = self.session
        return bool(
            session.editing
            and session.left_dragged
            and session.drag_candidate_index is not None
            and not session.add_point_active
            and not session.insert_point_active
        )

    def release_is_click(self, x_position: int, y_position: int) -> bool:
        if self.session.left_press_position is None:
            return False
        self.update_drag_state(x_position, y_position)
        is_click = not self.session.left_dragged
        self.session.left_press_position = None
        self.session.left_dragged = False
        return is_click

    def set_preview(
        self,
        *,
        point: object | None = None,
        valid: bool,
        snaps_closed: bool = False,
        snaps_to_mesh: bool = False,
        triangle_index: int | None = None,
        normal: object | None = None,
    ) -> ManualCurveActionResult:
        before = self.preview_signature()
        self.session.set_preview(
            point=point,
            valid=valid,
            snaps_closed=snaps_closed,
            snaps_to_mesh=snaps_to_mesh,
            triangle_index=triangle_index,
            normal=normal,
        )
        changed = before != self.preview_signature()
        return self._result(changed=changed, refresh=changed)

    def clear_preview(self) -> ManualCurveActionResult:
        changed = self.session.preview_valid or self.session.preview_point is not None
        self.session.clear_preview()
        return self._result(changed=changed, refresh=changed)

    def preview_signature(self) -> tuple[object, ...]:
        point = self.session.preview_point
        return (
            self.session.preview_valid,
            None if point is None else tuple(float(value) for value in point),
            self.session.preview_snaps_closed,
            self.session.preview_snaps_to_mesh,
            self.session.preview_triangle_index,
            None
            if self.session.preview_normal is None
            else tuple(self.session.preview_normal),
        )

    def insert_index_for_point(self, point: object) -> int:
        target = np.asarray(point, dtype=float).reshape(3)
        points = np.asarray(self.session.control_points, dtype=float).reshape((-1, 3))
        if len(points) < 2:
            return len(points)
        segment_count = len(points) if self.session.is_closed and len(points) >= 3 else len(points) - 1
        best_index = 1
        best_distance = float("inf")
        for segment_index in range(segment_count):
            distance = _distance_to_segment(
                target,
                points[segment_index],
                points[(segment_index + 1) % len(points)],
            )
            if distance < best_distance:
                best_distance = distance
                best_index = segment_index + 1
        return min(best_index, len(points))

    def selected_span_indices(self) -> list[int]:
        selected = self.session.selected_control_point_index
        count = len(self.session.control_points)
        if selected is None or count < 2:
            return []
        corners = {
            index
            for index, value in enumerate(self.session.point_types)
            if value == CURVE_POINT_CORNER
        }
        if not self.session.is_closed:
            left = max([0, *[index for index in corners if index <= selected]])
            right = min([count - 1, *[index for index in corners if index >= selected]])
            return list(range(left, right + 1))
        if not corners:
            return list(range(count))
        left = selected
        while left not in corners:
            left = (left - 1) % count
        right = selected
        while right not in corners or right == left:
            right = (right + 1) % count
            if right == left:
                return list(range(count))
        result = [left]
        while result[-1] != right:
            result.append((result[-1] + 1) % count)
        return result

    def smooth_selected_span(self) -> ManualCurveActionResult:
        indices = self.selected_span_indices()
        if len(indices) < 2:
            return self._result(
                success=False,
                status="Select a point inside a curve span first.",
            )
        for index in indices[1:-1]:
            self.session.point_types[index] = CURVE_POINT_SMOOTH
            self.session.point_type_sources[index] = CURVE_POINT_SOURCE_MANUAL
        self.invalidate_display_cache()
        return self._result(
            changed=True,
            status="Selected span set to smooth; corner endpoints preserved.",
            refresh=True,
        )

    def straighten_selected_span(self) -> ManualCurveActionResult:
        indices = self.selected_span_indices()
        if len(indices) < 2:
            return self._result(
                success=False,
                status="Select a point inside a curve span first.",
            )
        start = self.session.control_points[indices[0]].copy()
        end = self.session.control_points[indices[-1]].copy()
        for offset, index in enumerate(indices[1:-1], start=1):
            factor = offset / float(len(indices) - 1)
            self.session.control_points[index] = start * (1.0 - factor) + end * factor
            self.session.point_types[index] = CURVE_POINT_SMOOTH
            self.session.point_type_sources[index] = CURVE_POINT_SOURCE_MANUAL
        self.session.mark_controls_changed()
        self._auto_detect_all_if_enabled()
        self.invalidate_display_cache()
        return self._result(
            changed=True,
            status="Selected span straightened; endpoints preserved.",
            refresh=True,
        )

    def build_new_curve(
        self,
        *,
        curve_id: str,
        name: str,
        source_mesh_name: str | None = None,
        projection_mesh: TriangleMeshData | None = None,
        mesh_revision: object | None = None,
    ) -> ManualCurveActionResult:
        error = self._completion_error()
        if error:
            return self._result(success=False, status=error)
        snap_to_mesh = self.session.snapped_point_count > 0
        curve = self._build_curve(
            curve_id=curve_id,
            name=name,
            creation_type="curve_on_mesh" if snap_to_mesh else "manual",
            snap_to_mesh=snap_to_mesh,
            work_plane_type="mesh" if snap_to_mesh else self.session.plane_type,
            source_section_plane_id=(
                None if snap_to_mesh else self.session.source_section_plane_id
            ),
            source_mesh_name=source_mesh_name if snap_to_mesh else None,
        )
        self._project_curve_if_requested(
            curve,
            projection_mesh=projection_mesh,
            mesh_revision=mesh_revision,
            source_mesh_name=source_mesh_name,
        )
        return self._result(
            changed=True,
            status=f"Created {name}. Editing curve.",
            refresh=True,
            project_dirty=True,
            created_curve=curve,
            completed_curve_id=curve.id,
            warnings=_projection_warnings(curve),
            metadata=_projection_action_metadata(curve),
        )

    def build_updated_curve(
        self,
        curve: StoredCurve,
        *,
        projection_mesh: TriangleMeshData | None = None,
        mesh_revision: object | None = None,
        source_mesh_name: str | None = None,
    ) -> ManualCurveActionResult:
        error = self._completion_error()
        if error:
            return self._result(success=False, status=error)
        original_metadata = (
            dict(curve.metadata) if isinstance(curve.metadata, dict) else {}
        )
        snap_to_mesh = self.session.snap_to_mesh
        updated = self._build_curve(
            curve_id=curve.id,
            name=curve.name,
            creation_type=str(
                original_metadata.get(
                    "creation_type",
                    "curve_on_mesh" if snap_to_mesh else "manual",
                )
            ),
            snap_to_mesh=snap_to_mesh,
            work_plane_type=str(
                original_metadata.get(
                    "work_plane_type",
                    "mesh" if snap_to_mesh else self.session.plane_type,
                )
            ),
            source_section_plane_id=(
                None
                if snap_to_mesh
                else original_metadata.get("source_section_plane_id")
                or self.session.source_section_plane_id
            ),
            source_mesh_name=original_metadata.get("source_mesh_name") or source_mesh_name,
        )
        self._project_curve_if_requested(
            updated,
            projection_mesh=projection_mesh,
            mesh_revision=mesh_revision,
            source_mesh_name=source_mesh_name,
        )
        updated.metadata = self.merge_edit_metadata(
            original_metadata=original_metadata,
            updated_metadata=updated.metadata,
            updated_points=updated.fitted_points,
            is_closed=updated.is_closed,
        )
        updated.metadata["source_curve_revision"] = _revision(
            original_metadata.get("source_curve_revision", 0)
        ) + 1
        refresh_curve_diagnostics(updated)
        return self._result(
            changed=True,
            status="Curve edits saved",
            refresh=True,
            project_dirty=True,
            updated_curve=updated,
            completed_curve_id=curve.id,
            warnings=_projection_warnings(updated),
            metadata=_projection_action_metadata(updated),
        )

    def finish_new_curve(self, **kwargs: object) -> ManualCurveActionResult:
        return self.build_new_curve(**kwargs)

    def apply_curve_edits(
        self,
        curve: StoredCurve,
        **kwargs: object,
    ) -> ManualCurveActionResult:
        return self.build_updated_curve(curve, **kwargs)

    def simplify_stored_curve(
        self,
        curve: StoredCurve,
        *,
        curve_id: str,
        name: str,
        tolerance: float,
    ) -> ManualCurveActionResult:
        try:
            generated = simplify_curve(
                curve,
                curve_id=curve_id,
                name=name,
                tolerance=tolerance,
            )
        except CurveProcessingError as exc:
            return self._result(success=False, status=str(exc))
        return self._result(
            changed=True,
            created_curve=generated,
            project_dirty=True,
            status=(
                f"Created simplified curve ({curve.point_count} -> "
                f"{generated.point_count} points, tolerance {tolerance:.3f})"
            ),
        )

    def simplify_guide_curve(
        self,
        curve: StoredCurve,
        *,
        curve_id: str,
        name: str,
        tolerance: float,
        projection_mesh: TriangleMeshData | None = None,
        mesh_revision: object | None = None,
    ) -> ManualCurveActionResult:
        control_data = parse_manual_curve_metadata_v2(curve)
        if control_data is None:
            return self._result(
                success=False,
                status="Selected curve has no editable control points.",
            )
        reduced = simplify_manual_curve_control_data(
            control_data,
            tolerance=tolerance,
        )
        metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
        snap_to_mesh = bool(
            metadata.get("snap_to_mesh")
            or str(metadata.get("snap_mode", "")).strip().lower() == "mesh"
        )
        generated = build_manual_stored_curve(
            curve_id=curve_id,
            name=name,
            control_points=reduced.control_points,
            is_closed=reduced.is_closed,
            creation_type="manual",
            snap_to_mesh=snap_to_mesh,
            work_plane_type=str(
                metadata.get(
                    "work_plane_type", "mesh" if snap_to_mesh else "world_xy"
                )
            ),
            source_mesh_name=_optional_string(metadata.get("source_mesh_name")),
            snap_triangle_indices=[point.snap_triangle_index for point in reduced.points],
            snap_normals=[point.snap_normal for point in reduced.points],
            curve_method=MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
            sample_count=_sample_count(metadata.get("sample_count")),
            point_types=[point.point_type for point in reduced.points],
            point_type_sources=[
                str(point.metadata.get("point_type_source", CURVE_POINT_SOURCE_AUTO))
                for point in reduced.points
            ],
            preserve_corners=True,
            smoothness=_smoothness(metadata.get("smoothness")),
            keep_curve_on_mesh=bool(metadata.get("keep_curve_on_mesh", False)),
        )
        generated.metadata.update(
            {
                "source_curve_id": curve.id,
                "source_curve_name": curve.name,
                "simplification_tolerance": float(tolerance),
                "source_control_point_count": len(control_data.points),
                "result_control_point_count": len(reduced.points),
            }
        )
        self._project_curve_if_requested(
            generated,
            projection_mesh=projection_mesh,
            mesh_revision=mesh_revision,
            source_mesh_name=_optional_string(metadata.get("source_mesh_name")),
        )
        return self._result(
            changed=True,
            created_curve=generated,
            project_dirty=True,
            status=(
                f"Created simplified guide ({len(control_data.points)} -> "
                f"{len(reduced.points)} controls)."
            ),
        )

    def convert_curve_to_smooth(
        self,
        curve: StoredCurve,
        *,
        projection_mesh: TriangleMeshData | None = None,
        mesh_revision: object | None = None,
    ) -> ManualCurveActionResult:
        control_data = parse_manual_curve_metadata_v2(curve)
        if control_data is None:
            return self._result(
                success=False,
                status="Selected curve has no editable control points.",
            )
        metadata = dict(curve.metadata) if isinstance(curve.metadata, dict) else {}
        point_types: list[str] = []
        point_sources: list[str] = []
        for point in control_data.points:
            source = str(point.metadata.get("point_type_source", CURVE_POINT_SOURCE_AUTO))
            manual_corner = (
                point.point_type == CURVE_POINT_CORNER
                and source == CURVE_POINT_SOURCE_MANUAL
            )
            point_types.append(CURVE_POINT_CORNER if manual_corner else CURVE_POINT_SMOOTH)
            point_sources.append(source)
        snap_to_mesh = bool(
            metadata.get("snap_to_mesh")
            or str(metadata.get("snap_mode", "")).strip().lower() == "mesh"
        )
        updated = build_manual_stored_curve(
            curve_id=curve.id,
            name=curve.name,
            control_points=control_data.control_points,
            is_closed=control_data.is_closed,
            creation_type=str(metadata.get("creation_type", "manual")),
            snap_to_mesh=snap_to_mesh,
            work_plane_type=str(
                metadata.get(
                    "work_plane_type", "mesh" if snap_to_mesh else "world_xy"
                )
            ),
            source_section_plane_id=_optional_string(
                metadata.get("source_section_plane_id")
            ),
            source_mesh_name=_optional_string(metadata.get("source_mesh_name")),
            snap_triangle_indices=[point.snap_triangle_index for point in control_data.points],
            snap_normals=[point.snap_normal for point in control_data.points],
            curve_method=MANUAL_CURVE_METHOD_SMOOTH_GUIDE,
            sample_count=_sample_count(metadata.get("sample_count")),
            point_types=point_types,
            point_type_sources=point_sources,
            preserve_corners=True,
            smoothness=_smoothness(metadata.get("smoothness")),
            keep_curve_on_mesh=bool(metadata.get("keep_curve_on_mesh", snap_to_mesh)),
            control_point_revision=_revision(metadata.get("control_point_revision", 0)),
            corner_detection_revision=_revision(
                metadata.get("corner_detection_revision", 0)
            ),
        )
        updated.metadata = {**metadata, **updated.metadata}
        self._project_curve_if_requested(
            updated,
            projection_mesh=projection_mesh,
            mesh_revision=mesh_revision,
            source_mesh_name=_optional_string(metadata.get("source_mesh_name")),
        )
        return self._result(
            changed=True,
            updated_curve=updated,
            project_dirty=True,
            status="Converted selected curve to Smooth Curve.",
        )

    def display_state(
        self,
        *,
        projection_mesh: TriangleMeshData | None = None,
        mesh_revision: object | None = None,
    ) -> ManualCurveDisplayState:
        session = self.session
        if not session.active:
            return ManualCurveDisplayState(
                active=False,
                editing=False,
                control_points=None,
                point_types=None,
                fitted_points=None,
                is_closed=False,
                plane_normal=None,
                snap_to_mesh=False,
                selected_point_index=None,
                curve_method=DEFAULT_MANUAL_CURVE_METHOD,
                sample_count=DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
                preview_point=None,
                preview_valid=False,
                preview_snaps_closed=False,
                preview_snaps_to_mesh=False,
            )
        cache_key = self._display_key(
            mesh_revision=mesh_revision,
            projection_mesh=projection_mesh,
        )
        if cache_key != self._display_cache_key:
            fitted: np.ndarray | None = None
            if len(session.control_points) >= 2:
                fitted = sample_hybrid_manual_curve(session.to_control_data_v2())
                if session.keep_curve_on_mesh and projection_mesh is not None:
                    fitted = project_curve_points_to_mesh(
                        fitted,
                        projection_mesh,
                        preserve_missed_points=True,
                        mesh_query_service=self.mesh_query_service,
                        mesh_revision=mesh_revision,
                    ).projected_points
            self._display_fitted_points = fitted
            self._display_cache_key = cache_key
        return ManualCurveDisplayState(
            active=True,
            editing=session.editing,
            control_points=session.control_points,
            point_types=session.point_types,
            fitted_points=self._display_fitted_points,
            is_closed=session.is_closed,
            plane_normal=session.plane_normal,
            snap_to_mesh=session.snap_to_mesh,
            selected_point_index=(
                session.selected_control_point_index if session.editing else None
            ),
            curve_method=session.curve_method,
            sample_count=session.sample_count,
            preview_point=session.preview_point,
            preview_valid=session.preview_valid,
            preview_snaps_closed=session.preview_snaps_closed,
            preview_snaps_to_mesh=session.preview_snaps_to_mesh,
        )

    def invalidate_display_cache(self) -> None:
        self._display_cache_key = None
        self._display_fitted_points = None

    def status(self) -> str:
        session = self.session
        if session.editing:
            if session.add_point_active:
                return "Add Point active: left-click to append. Esc returns to edit mode."
            if session.insert_point_active:
                return "Insert Point active: click a curve segment. Esc returns to edit mode."
            return "Editing curve: select or drag control points. Right-drag to orbit."
        if session.submode == "inactive":
            return "Point placement paused. Press Add Point to continue."
        return "Drawing curve: left-click to add points. Right-drag to orbit."

    @staticmethod
    def merge_edit_metadata(
        *,
        original_metadata: dict[str, object],
        updated_metadata: dict[str, object],
        updated_points: np.ndarray,
        is_closed: bool,
    ) -> dict[str, object]:
        metadata = copy.deepcopy(original_metadata)
        metadata.update(copy.deepcopy(updated_metadata))
        creation_type = str(original_metadata.get("creation_type", "")).strip().lower()
        if creation_type not in {
            "region_boundary",
            "hybrid_region_guide",
            "projected_curve",
            "rebuilt_curve",
        }:
            return metadata
        metadata["creation_type"] = creation_type
        if creation_type == "region_boundary":
            points = np.asarray(updated_points, dtype=float).reshape((-1, 3))
            metadata["boundary_point_count"] = len(points)
            metadata["boundary_closed"] = bool(is_closed)
            metadata["boundary_perimeter"] = _polyline_perimeter(
                points, closed=is_closed
            )
        return metadata

    def _build_curve(
        self,
        *,
        curve_id: str,
        name: str,
        creation_type: str,
        snap_to_mesh: bool,
        work_plane_type: str,
        source_section_plane_id: object,
        source_mesh_name: object,
    ) -> StoredCurve:
        session = self.session
        session.normalize_parallel_arrays()
        curve = build_manual_stored_curve(
            curve_id=curve_id,
            name=name,
            control_points=np.asarray(session.control_points, dtype=float).reshape((-1, 3)),
            is_closed=session.is_closed,
            creation_type=creation_type,
            snap_to_mesh=snap_to_mesh,
            work_plane_type=work_plane_type,
            source_section_plane_id=_optional_string(source_section_plane_id),
            source_mesh_name=_optional_string(source_mesh_name),
            snap_triangle_indices=list(session.snap_triangle_indices),
            snap_normals=list(session.snap_normals),
            curve_method=session.curve_method,
            sample_count=session.sample_count,
            point_types=list(session.point_types),
            point_type_sources=list(session.point_type_sources),
            corner_angle_threshold_degrees=session.corner_angle_threshold_degrees,
            preserve_corners=session.preserve_corners,
            smoothness=session.smoothness,
            keep_curve_on_mesh=session.keep_curve_on_mesh,
            control_point_revision=session.control_point_revision,
            corner_detection_revision=session.corner_detection_revision,
        )
        self._apply_snap_metadata(curve)
        return curve

    def _apply_snap_metadata(self, curve: StoredCurve) -> None:
        distances = [
            None if value is None else float(value)
            for value in self.session.projection_distances
        ]
        curve.metadata.update(
            {
                "snap_triangle_indices": list(self.session.snap_triangle_indices),
                "snap_normals": copy.deepcopy(self.session.snap_normals),
                "snap_projection_distances": distances,
                "projection_distance": max(
                    [value for value in distances if value is not None],
                    default=0.0,
                ),
            }
        )

    def _project_curve_if_requested(
        self,
        curve: StoredCurve,
        *,
        projection_mesh: TriangleMeshData | None,
        mesh_revision: object | None,
        source_mesh_name: str | None,
    ) -> None:
        if not bool(curve.metadata.get("keep_curve_on_mesh", False)):
            return
        if projection_mesh is None:
            return
        projection = project_curve_points_to_mesh(
            curve.fitted_points,
            projection_mesh,
            preserve_missed_points=True,
            mesh_query_service=self.mesh_query_service,
            mesh_revision=mesh_revision,
        )
        curve.fitted_points = projection.projected_points
        curve.metadata.update(
            {
                "keep_curve_on_mesh": True,
                "projection_projected_count": projection.projected_count,
                "projection_missed_count": projection.missed_count,
                "projection_mean_distance": projection.mean_distance,
                "projection_max_distance": projection.max_distance,
                "projection_warnings": list(projection.warnings),
                "projection_failed_indices": list(projection.failed_indices),
                "projection_index_build_time_seconds": projection.build_time_seconds,
                "projection_query_time_seconds": projection.query_time_seconds,
                "projection_backend": projection.backend,
            }
        )
        if source_mesh_name:
            curve.metadata["source_mesh_name"] = source_mesh_name
        refresh_curve_diagnostics(curve)

    def _completion_error(self) -> str:
        count = len(self.session.control_points)
        if self.session.is_closed and count < 3:
            return "Manual Curve: closed curve needs at least 3 points"
        if not self.session.is_closed and count < 2:
            return "Manual Curve: open curve needs at least 2 points"
        return ""

    def _auto_detect_after_append(self) -> None:
        session = self.session
        if not session.auto_detect_corners or len(session.control_points) < 3:
            return
        detected = auto_detect_manual_curve_corners(
            session.to_control_data_v2(),
            threshold_degrees=session.corner_angle_threshold_degrees,
        )
        index = len(session.control_points) - 2
        session.point_types[index] = detected.points[index].point_type
        session.point_type_sources[index] = str(
            detected.points[index].metadata.get(
                "point_type_source", CURVE_POINT_SOURCE_AUTO
            )
        )
        session.corner_detection_revision = session.control_point_revision

    def _auto_detect_all_if_enabled(self) -> None:
        if self.session.auto_detect_corners and len(self.session.control_points) >= 3:
            detected = auto_detect_manual_curve_corners(
                self.session.to_control_data_v2(),
                threshold_degrees=self.session.corner_angle_threshold_degrees,
            )
            self._load_corner_classification(detected)

    def _load_corner_classification(self, control_data: ManualCurveControlDataV2) -> None:
        self.session.point_types = [point.point_type for point in control_data.points]
        self.session.point_type_sources = [
            str(point.metadata.get("point_type_source", CURVE_POINT_SOURCE_AUTO))
            for point in control_data.points
        ]
        self.session.corner_detection_revision = _revision(
            control_data.metadata.get(
                "corner_detection_revision",
                self.session.corner_detection_revision,
            )
        )

    def _display_option_key(self) -> tuple[object, ...]:
        session = self.session
        return (
            session.curve_method,
            session.sample_count,
            session.smoothness,
            session.preserve_corners,
            session.corner_angle_threshold_degrees,
            session.auto_detect_corners,
            session.snap_to_mesh,
            session.keep_curve_on_mesh,
        )

    def _display_key(
        self,
        *,
        mesh_revision: object | None,
        projection_mesh: TriangleMeshData | None,
    ) -> tuple[object, ...]:
        session = self.session
        mesh_token = (
            _stable_token(mesh_revision)
            if mesh_revision is not None
            else (
                None
                if projection_mesh is None
                else ("mesh_identity", id(projection_mesh))
            )
        )
        return (
            session.control_point_revision,
            session.curve_method,
            session.sample_count,
            session.smoothness,
            tuple(session.point_types),
            session.is_closed,
            session.keep_curve_on_mesh,
            mesh_token if session.keep_curve_on_mesh else None,
        )

    @staticmethod
    def _result(
        *,
        success: bool = True,
        changed: bool = False,
        status: str = "",
        refresh: bool = False,
        project_dirty: bool = False,
        created_curve: StoredCurve | None = None,
        updated_curve: StoredCurve | None = None,
        completed_curve_id: str | None = None,
        warnings: Sequence[str] = (),
        metadata: dict[str, object] | None = None,
    ) -> ManualCurveActionResult:
        return ManualCurveActionResult(
            success=success,
            changed=changed,
            status=status,
            needs_viewport_refresh=refresh,
            needs_ui_sync=True,
            project_dirty=project_dirty,
            created_curve=created_curve,
            updated_curve=updated_curve,
            completed_curve_id=completed_curve_id,
            warnings=tuple(str(value) for value in warnings),
            metadata={} if metadata is None else dict(metadata),
        )


def _finite_points(value: object) -> np.ndarray | None:
    try:
        points = np.asarray(value, dtype=float)
    except (TypeError, ValueError):
        return None
    if points.ndim != 2 or points.shape[1] != 3:
        return None
    points = points[np.all(np.isfinite(points), axis=1)]
    return points if len(points) else None


def _distance_to_segment(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    segment = end - start
    length_squared = float(np.dot(segment, segment))
    if length_squared <= 1e-12:
        return float(np.linalg.norm(point - start))
    factor = min(max(float(np.dot(point - start, segment) / length_squared), 0.0), 1.0)
    return float(np.linalg.norm(point - (start + factor * segment)))


def _stable_token(value: object) -> object:
    try:
        hash(value)
    except TypeError:
        return ("identity", id(value))
    return value


def _sample_count(value: object) -> int:
    try:
        count = int(value)
    except (TypeError, ValueError):
        count = DEFAULT_MANUAL_CURVE_SAMPLE_COUNT
    return min(max(count, 16), 2048)


def _smoothness(value: object) -> int:
    try:
        result = int(round(float(value)))
    except (TypeError, ValueError):
        result = DEFAULT_MANUAL_CURVE_SMOOTHNESS
    return min(max(result, 1), 8)


def _revision(value: object) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _polyline_perimeter(points: np.ndarray, *, closed: bool) -> float:
    values = np.asarray(points, dtype=float).reshape((-1, 3))
    if len(values) < 2:
        return 0.0
    perimeter = float(np.sum(np.linalg.norm(np.diff(values, axis=0), axis=1)))
    if closed and len(values) >= 3:
        perimeter += float(np.linalg.norm(values[0] - values[-1]))
    return perimeter


def _projection_warnings(curve: StoredCurve) -> tuple[str, ...]:
    warnings = curve.metadata.get("projection_warnings", [])
    if not isinstance(warnings, (list, tuple)):
        return ()
    return tuple(str(value) for value in warnings)


def _projection_action_metadata(curve: StoredCurve) -> dict[str, object]:
    keys = (
        "projection_projected_count",
        "projection_missed_count",
        "projection_mean_distance",
        "projection_max_distance",
        "projection_failed_indices",
        "projection_index_build_time_seconds",
        "projection_query_time_seconds",
        "projection_backend",
    )
    return {
        key: copy.deepcopy(curve.metadata[key])
        for key in keys
        if key in curve.metadata
    }
