"""UI-independent orchestration for mesh-region workflows."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import numpy as np

from application.controller_support import (
    CallbackUndoPayload,
    ControllerBase,
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
    is_region_boundary_curve,
    publish_scene_change,
)
from application.events import (
    ActiveToolChangedEvent,
    SelectionChangedEvent,
    StateChangedEvent,
)
from application.region_session import RegionSessionState
from application.results import CommandResult
from application.selection import SelectionKind, SelectionSnapshot
from application.state import AppState
from curves.curve_state import (
    CurveCollection,
    StoredCurve,
    add_curve,
    refresh_curve_diagnostics,
    set_active_curve,
    set_selected_curves,
)
from curves.manual_curve import (
    DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
    MANUAL_CURVE_METHOD_HYBRID,
    MANUAL_CURVE_METHOD_POLYLINE,
    ManualCurveControlDataV2,
    ManualCurvePoint,
    auto_detect_manual_curve_corners,
    build_manual_stored_curve,
    parse_manual_curve_metadata_v2,
)
from mesh.triangle_mesh import TriangleMeshData
from regions.boundary import RegionBoundaryPolyline, extract_region_boundary_polylines
from regions.region_state import RegionSelection, create_region_selection


SELECT_REGION = "region"
SELECT_CURVE = "curve"
REGION_TOOL_ID = "region_select"


@dataclass(slots=True)
class _CurveCreationSnapshot:
    curve_collection: CurveCollection
    curve_results: list[object]
    selected_item: str | None
    active_region_selected: bool

    @classmethod
    def capture(cls, state: AppState) -> _CurveCreationSnapshot:
        return cls(
            curve_collection=copy.deepcopy(state.curve_collection),
            curve_results=copy.deepcopy(list(state.curve_results)),
            selected_item=state.selected_item,
            active_region_selected=bool(
                state.region_collection.active_region is not None
                and state.region_collection.active_region.selected
            ),
        )

    def restore(self, state: AppState) -> None:
        state.curve_collection = copy.deepcopy(self.curve_collection)
        state.curve_results = copy.deepcopy(self.curve_results)
        state.selected_item = self.selected_item
        if state.region_collection.active_region is not None:
            state.region_collection.active_region.selected = self.active_region_selected


class RegionController(ControllerBase):
    """Coordinate transient region selection and derived boundary curves.

    Screen-space picking and mesh world transforms stay with presentation.  The
    adapter passes a resolved triangle index to :meth:`select_seed` and a mesh
    in the desired coordinate system to :meth:`extract_boundary`.
    """

    def __init__(
        self,
        state: AppState,
        *,
        events=None,
        session: RegionSessionState | None = None,
    ) -> None:
        super().__init__(state, events=events)
        self.session = session if session is not None else RegionSessionState()
        if not isinstance(self.session, RegionSessionState):
            raise TypeError("session must be a RegionSessionState.")

    def start(self) -> CommandResult:
        mesh_object = self.state.mesh_object
        if mesh_object is None or mesh_object.display_mesh.is_empty():
            return CommandResult.failure(
                "Region selection requires a loaded mesh.",
                status="Region selection requires a loaded mesh.",
            )
        was_active = self.session.active
        self.session.begin()
        if not was_active:
            self.events.publish(
                ActiveToolChangedEvent(
                    tool_id=REGION_TOOL_ID,
                    previous_tool_id=None,
                )
            )
        return CommandResult.ok(
            status="Region Select: click a mesh area.",
            changed=not was_active,
            dirty=False,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
        )

    def exit(self, *, status: str = "Region Select cancelled") -> CommandResult:
        was_active = self.session.active
        self.session.exit()
        if was_active:
            self.events.publish(
                ActiveToolChangedEvent(
                    tool_id=None,
                    previous_tool_id=REGION_TOOL_ID,
                )
            )
        return CommandResult.ok(
            status=status,
            changed=was_active,
            dirty=False,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
        )

    def configure(
        self,
        *,
        threshold_degrees: float | None = None,
        max_triangle_count: int | None = None,
    ) -> CommandResult:
        try:
            changed = self.session.configure(
                threshold_degrees=threshold_degrees,
                max_triangle_count=max_triangle_count,
            )
        except (TypeError, ValueError) as exc:
            return CommandResult.failure(str(exc), status=str(exc))
        if changed:
            self.events.publish(
                StateChangedEvent(
                    reason="region_controls_changed",
                    changed_fields=(
                        "region_threshold_degrees",
                        "region_max_triangle_count",
                    ),
                )
            )
        return CommandResult.ok(
            status=(
                f"Region controls: {self.session.threshold_degrees:.1f} degrees, "
                f"{self.session.max_triangle_count:,} triangles"
            ),
            changed=changed,
            dirty=False,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={
                "threshold_degrees": self.session.threshold_degrees,
                "max_triangle_count": self.session.max_triangle_count,
            },
        )

    def handle_pointer_event(
        self,
        event_type: str,
        x_position: int,
        y_position: int,
    ) -> CommandResult:
        """Route pointer gesture state without performing screen-space picks."""

        if not self.session.active:
            return CommandResult.ok(metadata={"consumed": False, "is_click": False})
        normalized = str(event_type).strip().lower()
        if normalized == "left_press":
            self.session.press(x_position, y_position)
            return CommandResult.ok(
                changed=True,
                metadata={"consumed": True, "is_click": False},
            )
        if normalized == "motion":
            had_press = self.session.left_press_position is not None
            dragged = self.session.motion(x_position, y_position)
            return CommandResult.ok(
                changed=had_press,
                metadata={"consumed": had_press, "is_click": False, "dragged": dragged},
            )
        if normalized == "left_release":
            had_press = self.session.left_press_position is not None
            is_click = self.session.release_is_click(x_position, y_position)
            return CommandResult.ok(
                status="Region Select: click a mesh area." if not is_click else "",
                changed=had_press,
                metadata={"consumed": had_press, "is_click": is_click},
            )
        if normalized in {"right_press", "right_release"}:
            return CommandResult.ok(
                metadata={"consumed": True, "is_click": False},
            )
        if normalized == "leave":
            had_press = self.session.left_press_position is not None
            self.session.clear_pointer()
            return CommandResult.ok(
                changed=had_press,
                metadata={"consumed": False, "is_click": False},
            )
        return CommandResult.ok(metadata={"consumed": False, "is_click": False})

    def select_seed(
        self,
        seed_triangle_index: int | None,
        *,
        mesh: TriangleMeshData | None = None,
        source_mesh_identifier: str | None = None,
        source_mesh_name: str | None = None,
    ) -> CommandResult:
        mesh_object = self.state.mesh_object
        region_mesh = mesh or (None if mesh_object is None else mesh_object.display_mesh)
        if region_mesh is None or region_mesh.is_empty():
            return CommandResult.failure("No mesh under cursor.", status="No mesh under cursor.")
        seed = self._valid_seed(region_mesh, seed_triangle_index)
        if seed is None:
            return CommandResult.failure("No mesh under cursor.", status="No mesh under cursor.")

        active_region = self.state.region_collection.active_region
        name = (
            active_region.name
            if active_region is not None and str(active_region.name).strip()
            else "Region 1"
        )
        identifier = (
            self._source_mesh_identifier(mesh_object)
            if source_mesh_identifier is None
            else str(source_mesh_identifier)
        )
        mesh_name = (
            "" if mesh_object is None else str(mesh_object.name)
        ) if source_mesh_name is None else str(source_mesh_name)
        region = create_region_selection(
            region_mesh,
            seed,
            source_mesh_identifier=identifier,
            source_mesh_name=mesh_name,
            threshold_degrees=self.session.threshold_degrees,
            max_triangle_count=self.session.max_triangle_count,
            name=name,
        )
        if region is None:
            return CommandResult.failure(
                "Region Select: no region found",
                status="Region Select: no region found",
            )

        previous_id = None if active_region is None else active_region.id
        region.visible = True
        region.selected = True
        self.state.clear_selection()
        if active_region is not None:
            active_region.selected = False
        self.state.region_collection.set_active(region)
        self.state.selected_item = SELECT_REGION
        self.session.set_seed(seed)
        self._publish_region_scene("region_selected", region.id, previous_id)
        self._publish_region_selection("region_selected")
        return CommandResult.ok(
            status=self._region_status("Selected region", region),
            changed=True,
            dirty=False,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={
                "region_id": region.id,
                "replaced_region_id": previous_id,
                "seed_triangle_index": seed,
                "triangle_count": len(region.triangle_indices),
            },
        )

    def recompute(self, *, mesh: TriangleMeshData | None = None) -> CommandResult:
        active_region = self.state.region_collection.active_region
        mesh_object = self.state.mesh_object
        region_mesh = mesh or (None if mesh_object is None else mesh_object.display_mesh)
        if active_region is None or region_mesh is None or region_mesh.is_empty():
            return CommandResult.failure("No region selection", status="No region selection")
        seed = self._valid_seed(region_mesh, active_region.seed_triangle_index)
        if seed is None:
            return CommandResult.failure(
                "Active region has no seed triangle",
                status="Active region has no seed triangle",
            )
        region = create_region_selection(
            region_mesh,
            seed,
            source_mesh_identifier=(
                active_region.source_mesh_identifier
                or self._source_mesh_identifier(mesh_object)
            ),
            source_mesh_name=(
                active_region.source_mesh_name
                or ("" if mesh_object is None else mesh_object.name)
            ),
            threshold_degrees=self.session.threshold_degrees,
            max_triangle_count=self.session.max_triangle_count,
            name=active_region.name or "Region 1",
        )
        if region is None:
            return CommandResult.failure(
                "Region Select: no region found",
                status="Region Select: no region found",
            )
        region.id = active_region.id
        region.visible = bool(active_region.visible)
        region.selected = True
        self.state.region_collection.set_active(region)
        self.state.selected_item = SELECT_REGION
        self.session.set_seed(seed)
        self._publish_region_scene("region_recomputed", region.id)
        self._publish_region_selection("region_recomputed")
        return CommandResult.ok(
            status=self._region_status("Recomputed region", region),
            changed=True,
            dirty=False,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={
                "region_id": region.id,
                "seed_triangle_index": seed,
                "triangle_count": len(region.triangle_indices),
            },
        )

    def clear(self) -> CommandResult:
        return self._remove_region(status_verb="cleared")

    def delete(self) -> CommandResult:
        return self._remove_region(status_verb="deleted")

    def hide(self) -> CommandResult:
        return self._set_visibility(False)

    def show(self) -> CommandResult:
        return self._set_visibility(True)

    def rename(self, name: str) -> CommandResult:
        region = self.state.region_collection.active_region
        if region is None:
            return CommandResult.failure("No region selection", status="No region selection")
        candidate = str(name).strip()
        if not candidate:
            return CommandResult.failure(
                "Region name must not be empty.",
                status="Region name must not be empty.",
            )
        old_name = region.name
        if candidate == old_name:
            return CommandResult.ok(status=f"Selected: {region.name}")
        region_id = region.id
        region.name = candidate

        def set_name(value: str, reason: str) -> None:
            current = self.state.region_collection.active_region
            if current is None or current.id != region_id:
                return
            current.name = value
            self._publish_region_scene(reason, region_id)

        self._publish_region_scene("region_renamed", region_id)
        return CommandResult.ok(
            status=f"Selected: {region.name}",
            changed=True,
            dirty=False,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=CallbackUndoPayload(
                name="Rename Region",
                undo_action=lambda: set_name(old_name, "undo_rename_region"),
                redo_action=lambda: set_name(candidate, "redo_rename_region"),
            ),
            metadata={
                "region_id": region_id,
                "old_name": old_name,
                "new_name": candidate,
            },
        )

    def extract_boundary(
        self,
        boundary_mesh: TriangleMeshData | None,
        *,
        weld_tolerance: float | None = None,
    ) -> CommandResult:
        if self.state.mesh_object is None or boundary_mesh is None or boundary_mesh.is_empty():
            return CommandResult.failure(
                "Region boundary extraction requires a loaded mesh.",
                status="Region boundary extraction requires a loaded mesh.",
            )
        region = self.state.region_collection.active_region
        if region is None:
            return CommandResult.failure(
                "No active region to extract.",
                status="No active region to extract.",
            )
        boundaries = extract_region_boundary_polylines(
            boundary_mesh,
            region,
            weld_tolerance=weld_tolerance,
        )
        if not boundaries:
            return CommandResult.failure(
                "No boundary edges found.",
                status="No boundary edges found.",
            )

        before = _CurveCreationSnapshot.capture(self.state)
        names = self._boundary_curve_names(len(boundaries))
        created = [
            self._stored_curve_from_boundary(boundary, index, name, region)
            for index, (boundary, name) in enumerate(zip(boundaries, names), start=1)
        ]
        try:
            self.state.clear_selection()
            for curve in created:
                add_curve(self.state.curve_collection, curve)
            set_selected_curves(
                self.state.curve_collection,
                (curve.id for curve in created),
                active_curve_id=created[0].id,
            )
        except ValueError as exc:
            before.restore(self.state)
            return CommandResult.failure(str(exc), status=str(exc))
        self.state.selected_item = SELECT_CURVE
        region.selected = False
        self._sync_curve_results()
        after = _CurveCreationSnapshot.capture(self.state)
        created_ids = tuple(curve.id for curve in created)
        undo = self._curve_creation_undo(
            "Extract Region Boundary",
            before,
            after,
            created_ids,
        )
        publish_scene_change(
            self.events,
            reason="region_boundary_extracted",
            object_ids=created_ids,
            changed_fields=("curve_collection", "selection"),
        )
        self._publish_curve_selection(created_ids, "region_boundary_extracted")
        return CommandResult.ok(
            status=self._boundary_status(created),
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo,
            metadata={
                "created_curve_ids": created_ids,
                "source_region_id": region.id,
            },
        )

    def select_boundary_curves(self) -> CommandResult:
        region = self.state.region_collection.active_region
        if region is None:
            return CommandResult.failure(
                "No active region to extract.",
                status="No active region to extract.",
            )
        curve_ids = tuple(
            curve.id
            for curve in self.state.curve_collection.curves
            if is_region_boundary_curve(curve)
            and str(curve.metadata.get("source_region_id", "")) == region.id
        )
        if not curve_ids:
            return CommandResult.failure(
                "No boundary curves linked to active region.",
                status="No boundary curves linked to active region.",
            )
        self.state.clear_selection()
        set_selected_curves(
            self.state.curve_collection,
            curve_ids,
            active_curve_id=curve_ids[0],
        )
        region.selected = False
        self.state.selected_item = SELECT_CURVE
        self._publish_curve_selection(curve_ids, "region_boundary_curves_selected")
        count = len(curve_ids)
        return CommandResult.ok(
            status=(
                "Selected 1 boundary curve."
                if count == 1
                else f"Selected {count} boundary curves."
            ),
            changed=True,
            dirty=False,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={"selected_curve_ids": curve_ids, "source_region_id": region.id},
        )

    def convert_boundary_to_hybrid_guide(self) -> CommandResult:
        source = self._active_curve()
        if source is None or not is_region_boundary_curve(source):
            return CommandResult.failure(
                "Select a region boundary curve to convert.",
                status="Select a region boundary curve to convert.",
            )
        control_data = parse_manual_curve_metadata_v2(source)
        if control_data is None:
            points = self._finite_points(source.fitted_points)
            if points is None:
                return CommandResult.failure(
                    "Selected boundary curve has no usable points.",
                    status="Selected boundary curve has no usable points.",
                )
            control_data = ManualCurveControlDataV2(
                points=[ManualCurvePoint(position=point) for point in points],
                is_closed=bool(source.is_closed),
                curve_method=MANUAL_CURVE_METHOD_HYBRID,
                sample_count=DEFAULT_MANUAL_CURVE_SAMPLE_COUNT,
            )
        if len(control_data.points) > 64:
            sample_indices = np.linspace(
                0,
                len(control_data.points) - 1,
                64,
                dtype=int,
            )
            control_data.points = [
                copy.deepcopy(control_data.points[int(index)])
                for index in sample_indices
            ]
        control_data.curve_method = MANUAL_CURVE_METHOD_HYBRID
        control_data = auto_detect_manual_curve_corners(control_data)
        before = _CurveCreationSnapshot.capture(self.state)
        guide = build_manual_stored_curve(
            curve_id=f"curve-{uuid4().hex}",
            name=self._derived_curve_name(f"{source.name} Guide"),
            control_points=control_data.control_points,
            is_closed=control_data.is_closed,
            creation_type="hybrid_region_guide",
            snap_to_mesh=bool(source.metadata.get("snap_to_mesh", False)),
            work_plane_type=str(source.metadata.get("work_plane_type", "mesh")),
            source_mesh_name=source.metadata.get("source_mesh_name"),
            curve_method=MANUAL_CURVE_METHOD_HYBRID,
            sample_count=control_data.sample_count,
            point_types=[point.point_type for point in control_data.points],
            corner_angle_threshold_degrees=control_data.corner_angle_threshold_degrees,
            preserve_corners=True,
        )
        guide.metadata.update(
            {
                "source_curve_id": source.id,
                "source_region_id": source.metadata.get("source_region_id", ""),
                "source_region_name": source.metadata.get("source_region_name", ""),
                "source_curve_tags": ["region_boundary", "hybrid_guide"],
            }
        )
        try:
            self.state.clear_selection()
            add_curve(self.state.curve_collection, guide)
            set_active_curve(self.state.curve_collection, guide.id)
        except ValueError as exc:
            before.restore(self.state)
            return CommandResult.failure(str(exc), status=str(exc))
        self.state.selected_item = SELECT_CURVE
        self._sync_curve_results()
        after = _CurveCreationSnapshot.capture(self.state)
        undo = self._curve_creation_undo(
            "Convert Boundary to Hybrid Guide Curve",
            before,
            after,
            (guide.id,),
        )
        publish_scene_change(
            self.events,
            reason="region_boundary_guide_created",
            object_ids=(guide.id,),
            changed_fields=("curve_collection", "selection"),
        )
        self._publish_curve_selection((guide.id,), "region_boundary_guide_created")
        return CommandResult.ok(
            status=f"Created hybrid guide curve: {guide.name}",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo,
            metadata={
                "created_curve_id": guide.id,
                "source_curve_id": source.id,
                "source_region_id": guide.metadata.get("source_region_id", ""),
            },
        )

    def _remove_region(self, *, status_verb: str) -> CommandResult:
        region = self.state.region_collection.active_region
        if region is None:
            return CommandResult.ok(status="No region selection")
        region_id = region.id
        selection_changed = self.state.selected_item == SELECT_REGION
        self.state.region_collection.clear()
        self.session.set_seed(None)
        if selection_changed:
            self.state.selected_item = None
        self._publish_region_scene(f"region_{status_verb}", region_id)
        if selection_changed:
            self.events.publish(
                SelectionChangedEvent(
                    SelectionSnapshot(),
                    reason=f"region_{status_verb}",
                )
            )
        return CommandResult.ok(
            status=f"Region {status_verb}.",
            changed=True,
            dirty=False,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={"removed_region_id": region_id},
        )

    def _set_visibility(self, visible: bool) -> CommandResult:
        region = self.state.region_collection.active_region
        if region is None:
            return CommandResult.failure("No region selection", status="No region selection")
        changed = bool(region.visible) != bool(visible)
        region.visible = bool(visible)
        self._publish_region_scene(
            "region_shown" if visible else "region_hidden",
            region.id,
        )
        return CommandResult.ok(
            status="Region shown." if visible else "Region hidden.",
            changed=changed,
            dirty=False,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            metadata={"region_id": region.id, "visible": bool(visible)},
        )

    def _curve_creation_undo(
        self,
        name: str,
        before: _CurveCreationSnapshot,
        after: _CurveCreationSnapshot,
        curve_ids: tuple[str, ...],
    ) -> CallbackUndoPayload:
        def restore(snapshot: _CurveCreationSnapshot, reason: str) -> None:
            snapshot.restore(self.state)
            publish_scene_change(
                self.events,
                reason=reason,
                object_ids=curve_ids,
                changed_fields=("curve_collection", "selection"),
            )
            selected = tuple(self.state.curve_collection.selected_curve_ids)
            self._publish_curve_selection(selected, reason)

        token = name.lower().replace(" ", "_")
        return CallbackUndoPayload(
            name=name,
            undo_action=lambda: restore(before, f"undo_{token}"),
            redo_action=lambda: restore(after, f"redo_{token}"),
        )

    def _stored_curve_from_boundary(
        self,
        boundary: RegionBoundaryPolyline,
        index: int,
        name: str,
        region: RegionSelection,
    ) -> StoredCurve:
        points = np.asarray(boundary.points, dtype=float).reshape((-1, 3))
        curve = build_manual_stored_curve(
            curve_id=f"curve-{uuid4().hex}",
            name=name,
            control_points=points,
            is_closed=bool(boundary.is_closed),
            creation_type="region_boundary",
            snap_to_mesh=False,
            work_plane_type="mesh",
            source_mesh_name=boundary.source_mesh_name,
            curve_method=MANUAL_CURVE_METHOD_POLYLINE,
            sample_count=max(len(points), 2),
        )
        metadata = dict(curve.metadata)
        metadata.update(boundary.metadata)
        metadata.update(
            {
                "creation_type": "region_boundary",
                "source_region_id": boundary.source_region_id,
                "source_region_name": region.name,
                "source_mesh_name": boundary.source_mesh_name,
                "curve_method": MANUAL_CURVE_METHOD_POLYLINE,
                "source_curve_tags": ["region_boundary"],
                "boundary_point_count": int(len(points)),
                "boundary_closed": bool(boundary.is_closed),
                "boundary_perimeter": self._polyline_perimeter(
                    points,
                    closed=bool(boundary.is_closed),
                ),
                "region_triangle_count": len(region.triangle_indices),
                "source_region_triangle_count": len(region.triangle_indices),
                "boundary_index": int(index),
            }
        )
        curve.metadata = metadata
        curve.original_points = points.copy()
        curve.fitted_points = points.copy()
        curve.is_closed = bool(boundary.is_closed)
        refresh_curve_diagnostics(curve)
        return curve

    def _boundary_curve_names(self, count: int) -> list[str]:
        existing = {curve.name for curve in self.state.curve_collection.curves}
        names: list[str] = []
        index = 1
        while len(names) < int(count):
            candidate = f"Region Boundary {index}"
            index += 1
            if candidate in existing:
                continue
            existing.add(candidate)
            names.append(candidate)
        return names

    def _derived_curve_name(self, prefix: str) -> str:
        existing = {curve.name for curve in self.state.curve_collection.curves}
        index = 1
        while f"{prefix} {index}" in existing:
            index += 1
        return f"{prefix} {index}"

    def _active_curve(self) -> StoredCurve | None:
        active_id = self.state.curve_collection.active_curve_id
        return next(
            (
                curve
                for curve in self.state.curve_collection.curves
                if curve.id == active_id
            ),
            None,
        )

    def _sync_curve_results(self) -> None:
        for curve in self.state.curve_collection.curves:
            refresh_curve_diagnostics(curve)
        self.state.curve_results = [
            curve for curve in self.state.curve_collection.curves if bool(curve.visible)
        ]

    def _publish_region_scene(self, reason: str, *region_ids: str | None) -> None:
        ids = tuple(str(value) for value in region_ids if value)
        publish_scene_change(
            self.events,
            reason=reason,
            object_ids=ids,
            changed_fields=("region_collection",),
        )

    def _publish_region_selection(self, reason: str) -> None:
        region = self.state.region_collection.active_region
        ids = () if region is None or not region.selected else (region.id,)
        self.events.publish(
            SelectionChangedEvent(
                SelectionSnapshot.from_ids(ids, kind=SelectionKind.REGION),
                reason=reason,
            )
        )

    def _publish_curve_selection(self, ids: tuple[str, ...], reason: str) -> None:
        ordered = tuple(
            curve.id
            for curve in self.state.curve_collection.curves
            if curve.id in set(ids)
        )
        primary = self.state.curve_collection.active_curve_id
        if primary not in ordered:
            primary = ordered[0] if ordered else None
        self.events.publish(
            SelectionChangedEvent(
                SelectionSnapshot.from_ids(
                    ordered,
                    kind=SelectionKind.CURVE,
                    primary_id=primary,
                ),
                reason=reason,
            )
        )

    @staticmethod
    def _valid_seed(mesh: TriangleMeshData, value: object) -> int | None:
        try:
            seed = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError, OverflowError):
            return None
        return seed if 0 <= seed < len(mesh.triangles) else None

    @staticmethod
    def _source_mesh_identifier(mesh_object: object | None) -> str:
        if mesh_object is None:
            return ""
        file_path = getattr(mesh_object, "file_path", None)
        if isinstance(file_path, Path) or file_path is not None:
            return str(file_path)
        name = str(getattr(mesh_object, "name", ""))
        return name or str(id(getattr(mesh_object, "display_mesh", mesh_object)))

    @staticmethod
    def _region_status(prefix: str, region: RegionSelection) -> str:
        count = len(region.triangle_indices)
        label = "triangle" if count == 1 else "triangles"
        return f"{prefix}: {count:,} {label} at {region.threshold_degrees:.1f}\N{DEGREE SIGN}."

    @staticmethod
    def _boundary_status(curves: list[StoredCurve]) -> str:
        if len(curves) == 1:
            shape = "closed" if curves[0].is_closed else "open"
            return f"Extracted 1 {shape} boundary curve."
        return f"Extracted {len(curves)} boundary curves."

    @staticmethod
    def _polyline_perimeter(points: np.ndarray, *, closed: bool) -> float:
        if len(points) < 2:
            return 0.0
        length = float(np.linalg.norm(np.diff(points, axis=0), axis=1).sum())
        if closed and len(points) >= 3:
            length += float(np.linalg.norm(points[0] - points[-1]))
        return length

    @staticmethod
    def _finite_points(value: object) -> np.ndarray | None:
        try:
            points = np.asarray(value, dtype=float).reshape((-1, 3))
        except (TypeError, ValueError):
            return None
        if len(points) < 2 or not np.all(np.isfinite(points)):
            return None
        return points


__all__ = ("REGION_TOOL_ID", "RegionController", "RegionSessionState")
