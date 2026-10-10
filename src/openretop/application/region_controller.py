"""UI-independent orchestration for mesh-region workflows.

A region's boundary becomes Surface Sketch curves (lofted, filled, edited like any sketch curve).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from openretop.application.controller_support import (
    MODEL_SYNC_UI_REQUESTS,
    MODEL_SYNC_VIEWPORT_REQUESTS,
    CallbackUndoPayload,
    ControllerBase,
    publish_scene_change,
)
from openretop.application.events import (
    ActiveToolChangedEvent,
    SelectionChangedEvent,
    StateChangedEvent,
)
from openretop.application.region_session import RegionSessionState
from openretop.application.results import CommandResult
from openretop.application.selection import SelectionKind, SelectionSnapshot
from openretop.application.state import AppState
from openretop.mesh.triangle_mesh import TriangleMeshData
from openretop.regions.boundary import extract_region_boundary_polylines
from openretop.regions.region_state import RegionSelection, create_region_selection

SELECT_REGION = "region"
REGION_TOOL_ID = "region_select"


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

        model = self.state.model
        before = model.snapshot()
        matrix = getattr(self.state.mesh_object, "transform_matrix", None)
        matrix = np.identity(4) if matrix is None else np.asarray(matrix, dtype=float).reshape(4, 4)
        created: list[str] = []
        names = self._boundary_curve_names(len(boundaries))
        for boundary, name in zip(boundaries, names, strict=True):
            local = np.asarray(boundary.points, dtype=float).reshape(-1, 3)
            world = local @ matrix[:3, :3].T + matrix[:3, 3]  # the display mesh is in the scan's own coordinates
            if len(world) < 2:
                continue
            created.append(model.sketch.add_polyline_curve(world, closed=bool(boundary.is_closed), name=name).id)
        if not created:
            return CommandResult.failure("No boundary edges found.", status="No boundary edges found.")
        model.selected_curve_ids = list(created)
        model.revision += 1
        region.selected = False
        after = model.snapshot()

        def restore(snapshot: object, reason: str) -> None:
            model.restore(snapshot)  # type: ignore[arg-type]
            publish_scene_change(self.events, reason=reason, object_ids=tuple(created), changed_fields=("model",))

        undo = CallbackUndoPayload(
            name="Extract Region Boundary",
            undo_action=lambda: restore(before, "undo_extract_region_boundary"),
            redo_action=lambda: restore(after, "redo_extract_region_boundary"),
        )
        publish_scene_change(self.events, reason="region_boundary_extracted", object_ids=tuple(created), changed_fields=("model",))
        count = len(created)
        return CommandResult.ok(
            status=f"Extracted {count} boundary curve{'s' if count != 1 else ''} into the Surface Sketch.",
            changed=True,
            dirty=True,
            viewport_requests=MODEL_SYNC_VIEWPORT_REQUESTS,
            ui_requests=MODEL_SYNC_UI_REQUESTS,
            undo_payload=undo,
            metadata={"created_curve_ids": tuple(created), "source_region_id": region.id},
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

    def _boundary_curve_names(self, count: int) -> list[str]:
        existing = {curve.name for curve in self.state.model.sketch.curves}
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



__all__ = ("REGION_TOOL_ID", "RegionController", "RegionSessionState")
