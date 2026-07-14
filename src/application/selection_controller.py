"""UI-independent selection workflow controller."""

from __future__ import annotations

from collections.abc import Iterable

from application.controller_support import (
    ControllerBase,
    SELECTION_SYNC_UI_REQUESTS,
    SELECTION_SYNC_VIEWPORT_REQUESTS,
    curve_ids_for_group,
)
from application.events import SelectionChangedEvent, StateChangedEvent
from application.results import CommandResult
from application.scene_ids import (
    NODE_BREP_SURFACES,
    NODE_CURVES,
    NODE_MESH,
    NODE_REGIONS,
    NODE_SECTION_PLANES,
    NODE_SECTION_RESULTS,
    NODE_SURFACES,
    curve_group_id_from_node,
    curve_id_from_node,
    curve_node_id,
    region_id_from_node,
    region_node_id,
    section_plane_id_from_node,
    section_plane_node_id,
    section_result_id_from_node,
    section_result_node_id,
    surface_id_from_node,
    surface_node_id,
)
from application.selection import SelectionItem, SelectionKind, SelectionSnapshot
from curves.curve_state import (
    clear_curve_selection,
    set_active_curve,
    set_selected_curves,
)
from sections.section_state import (
    clear_plane_selection,
    clear_result_selection,
    get_active_plane,
    get_active_result,
    set_active_plane,
    set_active_result,
    set_selected_planes,
    set_selected_results,
)
from surfaces.brep_state import (
    clear_brep_surface_selection,
    set_active_brep_surface,
    set_selected_brep_surfaces,
)
from surfaces.surface_state import (
    clear_surface_selection,
    set_active_surface,
    set_selected_surfaces,
)


SELECT_MODEL = "model"
SELECT_SECTION_PLANE = "section_plane"
SELECT_SECTION_RESULT = "section_result"
SELECT_CURVE = "curve"
SELECT_SURFACE = "surface"
SELECT_REGION = "region"


class SelectionController(ControllerBase):
    """Coordinate collection selection without widgets, actors, or dialogs."""

    def snapshot(self) -> SelectionSnapshot:
        """Implement the Task 75 ``SelectionProvider`` port."""

        state = self.state
        selected_item = state.selected_item
        items: list[SelectionItem] = []
        primary_id: str | None = None

        if selected_item == SELECT_MODEL and state.mesh_object is not None:
            items.append(SelectionItem(NODE_MESH, SelectionKind.MESH))
            primary_id = NODE_MESH
        elif selected_item == SELECT_SECTION_PLANE:
            active_id = state.section_collection.active_plane_id
            for plane in state.section_collection.planes:
                if plane.id in state.section_collection.selected_plane_ids:
                    items.append(
                        SelectionItem(
                            section_plane_node_id(plane.id),
                            SelectionKind.SECTION_PLANE,
                        )
                    )
            if active_id in state.section_collection.selected_plane_ids:
                primary_id = section_plane_node_id(active_id)
        elif selected_item == SELECT_SECTION_RESULT:
            active_id = state.section_collection.active_result_id
            for result in state.section_collection.results:
                if result.id in state.section_collection.selected_result_ids:
                    items.append(
                        SelectionItem(
                            section_result_node_id(result.id),
                            SelectionKind.SECTION_RESULT,
                        )
                    )
            if active_id in state.section_collection.selected_result_ids:
                primary_id = section_result_node_id(active_id)
            for curve in state.curve_collection.curves:
                if curve.id in state.curve_collection.selected_curve_ids:
                    items.append(
                        SelectionItem(curve_node_id(curve.id), SelectionKind.CURVE)
                    )
        elif selected_item == SELECT_CURVE:
            active_id = state.curve_collection.active_curve_id
            for curve in state.curve_collection.curves:
                if curve.id in state.curve_collection.selected_curve_ids:
                    items.append(
                        SelectionItem(curve_node_id(curve.id), SelectionKind.CURVE)
                    )
            if active_id in state.curve_collection.selected_curve_ids:
                primary_id = curve_node_id(active_id)
        elif selected_item == SELECT_SURFACE:
            active_preview_id = state.surface_collection.active_surface_id
            active_brep_id = state.brep_surface_collection.active_surface_id
            for surface in state.surface_collection.surfaces:
                if surface.id in state.surface_collection.selected_surface_ids:
                    items.append(
                        SelectionItem(surface_node_id(surface.id), SelectionKind.SURFACE)
                    )
            for surface in state.brep_surface_collection.surfaces:
                node_id = surface_node_id(surface.id)
                if (
                    surface.id in state.brep_surface_collection.selected_surface_ids
                    and all(item.id != node_id for item in items)
                ):
                    items.append(SelectionItem(node_id, SelectionKind.SURFACE))
            if active_preview_id in state.surface_collection.selected_surface_ids:
                primary_id = surface_node_id(active_preview_id)
            elif active_brep_id in state.brep_surface_collection.selected_surface_ids:
                primary_id = surface_node_id(active_brep_id)
        elif selected_item == SELECT_REGION:
            region = state.region_collection.active_region
            if region is not None and region.selected:
                items.append(
                    SelectionItem(region_node_id(region.id), SelectionKind.REGION)
                )
                primary_id = region_node_id(region.id)

        if items and primary_id is None:
            primary_id = items[0].id
        return SelectionSnapshot(tuple(items), primary_id=primary_id)

    def clear(self, *, status: str = "No selection") -> CommandResult:
        before = self._before_selection()
        self.state.clear_selection()
        region = self.state.region_collection.active_region
        if region is not None:
            region.selected = False
        return self._selection_result(before, reason="selection_cleared", status=status)

    def select_model(self) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        before = self._before_selection()
        self._clear_families(keep=set())
        self.state.selected_item = SELECT_MODEL
        self._clear_transform_session()
        return self._selection_result(
            before,
            reason="model_selected",
            status=f"Selected: {self.state.mesh_object.name}",
        )

    def select_section_plane(self, plane_id: str | None = None) -> CommandResult:
        active = get_active_plane(self.state.section_collection)
        target_id = str(plane_id) if plane_id is not None else (
            None if active is None else active.id
        )
        if target_id is None:
            return CommandResult.failure(
                "No section plane is available.", status="No selection"
            )
        return self.select_section_planes((target_id,), active_plane_id=target_id)

    def select_section_planes(
        self,
        plane_ids: Iterable[str],
        *,
        active_plane_id: str | None = None,
    ) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        requested = tuple(dict.fromkeys(str(value) for value in plane_ids))
        if not requested:
            return CommandResult.failure(
                "No section planes are available.",
                status="No section planes available",
            )
        before = self._before_selection()
        try:
            set_selected_planes(
                self.state.section_collection,
                list(requested),
                active_plane_id=active_plane_id,
            )
        except ValueError as exc:
            return CommandResult.failure(str(exc), status="Section plane not found")
        self._clear_families(keep={SELECT_SECTION_PLANE})
        self.state.selected_item = SELECT_SECTION_PLANE
        self._clear_transform_session()
        count = len(self.state.section_collection.selected_plane_ids)
        status = (
            "Selected: Section Plane"
            if count == 1
            else f"Selected: {count} section planes"
        )
        return self._selection_result(
            before, reason="section_planes_selected", status=status
        )

    def select_section_result(self, result_id: str | None = None) -> CommandResult:
        active = get_active_result(self.state.section_collection)
        target_id = str(result_id) if result_id is not None else (
            None if active is None else active.id
        )
        if target_id is None:
            return CommandResult.failure(
                "No section result is available.", status="No selection"
            )
        return self.select_section_results((target_id,), active_result_id=target_id)

    def select_section_results(
        self,
        result_ids: Iterable[str],
        *,
        active_result_id: str | None = None,
    ) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        requested = tuple(dict.fromkeys(str(value) for value in result_ids))
        if not requested:
            return CommandResult.failure(
                "No section results are available.",
                status="No section results available",
            )
        before = self._before_selection()
        try:
            set_selected_results(
                self.state.section_collection,
                list(requested),
                active_result_id=active_result_id,
            )
        except ValueError as exc:
            return CommandResult.failure(str(exc), status="Section result not found")

        selected_result_ids = self.state.section_collection.selected_result_ids
        child_curve_ids = [
            curve.id
            for curve in self.state.curve_collection.curves
            if curve.section_result_id in selected_result_ids
        ]
        if child_curve_ids:
            set_selected_curves(
                self.state.curve_collection,
                child_curve_ids,
                active_curve_id=child_curve_ids[0],
            )
        else:
            clear_curve_selection(self.state.curve_collection)
        self._clear_families(keep={SELECT_SECTION_RESULT, SELECT_CURVE})
        self.state.selected_item = SELECT_SECTION_RESULT
        self._clear_transform_session()
        active = get_active_result(self.state.section_collection)
        self.state.section_result = (
            active.result if active is not None and active.visible else None
        )
        count = len(selected_result_ids)
        status = (
            f"Selected: {active.name}"
            if count == 1 and active is not None
            else f"Selected: {count} section results"
        )
        return self._selection_result(
            before, reason="section_results_selected", status=status
        )

    def select_curve(self, curve_id: str | None = None) -> CommandResult:
        target_id = str(curve_id) if curve_id is not None else (
            self.state.curve_collection.active_curve_id
        )
        if target_id is None:
            return CommandResult.failure("No curve is available.", status="No selection")
        return self.select_curves((target_id,), active_curve_id=target_id)

    def select_curves(
        self,
        curve_ids: Iterable[str],
        *,
        active_curve_id: str | None = None,
    ) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        requested = tuple(dict.fromkeys(str(value) for value in curve_ids))
        if not requested:
            return self.clear()
        before = self._before_selection()
        try:
            set_selected_curves(
                self.state.curve_collection,
                list(requested),
                active_curve_id=active_curve_id,
            )
        except ValueError as exc:
            return CommandResult.failure(str(exc), status="Curve not found")
        self._clear_families(keep={SELECT_CURVE})
        self.state.selected_item = SELECT_CURVE
        self._clear_transform_session()
        active = next(
            (
                curve
                for curve in self.state.curve_collection.curves
                if curve.id == self.state.curve_collection.active_curve_id
            ),
            None,
        )
        count = len(self.state.curve_collection.selected_curve_ids)
        status = (
            f"Selected: {active.name}"
            if count == 1 and active is not None
            else f"Selected: {count} curves"
        )
        return self._selection_result(before, reason="curves_selected", status=status)

    def select_surface(self, surface_id: str | None = None) -> CommandResult:
        target_id = str(surface_id) if surface_id is not None else (
            self.state.surface_collection.active_surface_id
            or self.state.brep_surface_collection.active_surface_id
        )
        if target_id is None:
            return CommandResult.failure("No surface is available.", status="No selection")
        return self.select_surfaces((target_id,), active_surface_id=target_id)

    def select_surfaces(
        self,
        surface_ids: Iterable[str],
        *,
        active_surface_id: str | None = None,
    ) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        requested = tuple(dict.fromkeys(str(value) for value in surface_ids))
        if not requested:
            return CommandResult.failure(
                "No surfaces are available.", status="No surfaces available"
            )
        preview_available = {
            surface.id for surface in self.state.surface_collection.surfaces
        }
        brep_available = {
            surface.id for surface in self.state.brep_surface_collection.surfaces
        }
        ambiguous = set(requested) & preview_available & brep_available
        if ambiguous:
            return CommandResult.failure(
                f"Surface ID is ambiguous: {sorted(ambiguous)[0]}",
                status="Surface not found",
            )
        preview_ids = [value for value in requested if value in preview_available]
        brep_ids = [value for value in requested if value in brep_available]
        if len(preview_ids) + len(brep_ids) != len(requested):
            return CommandResult.failure("Surface not found.", status="Surface not found")
        active_candidate = (
            active_surface_id if active_surface_id in requested else requested[0]
        )
        before = self._before_selection()
        if preview_ids:
            set_selected_surfaces(
                self.state.surface_collection,
                preview_ids,
                active_surface_id=(
                    active_candidate
                    if active_candidate in preview_ids
                    else preview_ids[0]
                ),
            )
        else:
            clear_surface_selection(self.state.surface_collection)
        if brep_ids:
            set_selected_brep_surfaces(
                self.state.brep_surface_collection,
                brep_ids,
                active_surface_id=(
                    active_candidate if active_candidate in brep_ids else brep_ids[0]
                ),
            )
        else:
            clear_brep_surface_selection(self.state.brep_surface_collection)
        if preview_ids and brep_ids:
            if active_candidate in preview_ids:
                self.state.brep_surface_collection.active_surface_id = None
            else:
                self.state.surface_collection.active_surface_id = None
        self._clear_families(keep={SELECT_SURFACE})
        self.state.selected_item = SELECT_SURFACE
        self._clear_transform_session()
        count = len(preview_ids) + len(brep_ids)
        active_name = next(
            (
                surface.name
                for surface in (
                    *self.state.surface_collection.surfaces,
                    *self.state.brep_surface_collection.surfaces,
                )
                if surface.id == active_candidate
            ),
            "Surface",
        )
        status = (
            f"Selected: {active_name}"
            if count == 1
            else f"Selected: {count} surfaces"
        )
        return self._selection_result(before, reason="surfaces_selected", status=status)

    def select_region(self, region_id: str | None = None) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("No mesh is loaded.", status="No selection")
        region = self.state.region_collection.active_region
        if region is None:
            return CommandResult.failure("No region is available.", status="No selection")
        if region_id is not None and region.id != str(region_id):
            return CommandResult.failure("Region not found.", status="Region not found")
        before = self._before_selection()
        self._clear_families(keep={SELECT_REGION})
        region.selected = True
        self.state.selected_item = SELECT_REGION
        self._clear_transform_session()
        return self._selection_result(
            before,
            reason="region_selected",
            status=f"Selected: {region.name or 'Region 1'}",
        )

    def select_nodes(
        self,
        node_ids: Iterable[str],
        *,
        primary_id: str | None = None,
    ) -> CommandResult:
        """Resolve one homogeneous scene-node selection into a typed operation."""

        nodes = tuple(dict.fromkeys(str(value) for value in node_ids if str(value)))
        if not nodes:
            return self.clear()
        if NODE_MESH in nodes:
            return self.select_model() if len(nodes) == 1 else CommandResult.failure(
                "Selection must contain one object family."
            )

        plane_ids = [value for value in map(section_plane_id_from_node, nodes) if value]
        result_ids = [value for value in map(section_result_id_from_node, nodes) if value]
        curve_ids = [value for value in map(curve_id_from_node, nodes) if value]
        surface_ids = [value for value in map(surface_id_from_node, nodes) if value]
        region_ids = [value for value in map(region_id_from_node, nodes) if value]
        if nodes == (NODE_SECTION_PLANES,):
            plane_ids = [plane.id for plane in self.state.section_collection.planes]
        elif nodes == (NODE_SECTION_RESULTS,):
            result_ids = [result.id for result in self.state.section_collection.results]
        elif nodes == (NODE_CURVES,):
            curve_ids = [curve.id for curve in self.state.curve_collection.curves]
        elif len(nodes) == 1 and curve_group_id_from_node(nodes[0]) is not None:
            curve_ids = list(
                curve_ids_for_group(self.state, curve_group_id_from_node(nodes[0]) or "")
            )
        elif nodes == (NODE_SURFACES,):
            surface_ids = [surface.id for surface in self.state.surface_collection.surfaces]
        elif nodes == (NODE_BREP_SURFACES,):
            surface_ids = [
                surface.id for surface in self.state.brep_surface_collection.surfaces
            ]
        elif nodes == (NODE_REGIONS,):
            region = self.state.region_collection.active_region
            region_ids = [] if region is None else [region.id]

        families = [
            values
            for values in (plane_ids, result_ids, curve_ids, surface_ids, region_ids)
            if values
        ]
        if len(families) != 1:
            return CommandResult.failure("Selection must contain one object family.")
        primary_object_id = None
        if primary_id is not None:
            primary_object_id = next(
                (
                    value
                    for parser in (
                        section_plane_id_from_node,
                        section_result_id_from_node,
                        curve_id_from_node,
                        surface_id_from_node,
                        region_id_from_node,
                    )
                    if (value := parser(primary_id)) is not None
                ),
                None,
            )
        if plane_ids:
            return self.select_section_planes(
                plane_ids, active_plane_id=primary_object_id
            )
        if result_ids:
            return self.select_section_results(
                result_ids, active_result_id=primary_object_id
            )
        if curve_ids:
            return self.select_curves(curve_ids, active_curve_id=primary_object_id)
        if surface_ids:
            return self.select_surfaces(
                surface_ids, active_surface_id=primary_object_id
            )
        return self.select_region(region_ids[0])

    def _before_selection(self) -> tuple[SelectionSnapshot, tuple[object, ...]]:
        state = self.state
        return (
            self.snapshot(),
            (
                state.active_transform_mode,
                state.active_transform_axis,
                None if state.transform_state is None else id(state.transform_state),
            ),
        )

    def _selection_result(
        self,
        before: tuple[SelectionSnapshot, tuple[object, ...]],
        *,
        reason: str,
        status: str,
    ) -> CommandResult:
        after = self.snapshot()
        transform_after = (
            self.state.active_transform_mode,
            self.state.active_transform_axis,
            (
                None
                if self.state.transform_state is None
                else id(self.state.transform_state)
            ),
        )
        changed = before[0] != after or before[1] != transform_after
        if changed:
            self.events.publish(SelectionChangedEvent(after, reason=reason))
            self.events.publish(
                StateChangedEvent(reason=reason, changed_fields=("selection",))
            )
        return CommandResult.ok(
            status=status,
            changed=changed,
            dirty=False,
            viewport_requests=(SELECTION_SYNC_VIEWPORT_REQUESTS if changed else ()),
            ui_requests=(SELECTION_SYNC_UI_REQUESTS if changed else ()),
            metadata={"selection": after},
        )

    def _clear_families(self, *, keep: set[str]) -> None:
        state = self.state
        if SELECT_SECTION_PLANE not in keep:
            clear_plane_selection(state.section_collection)
        if SELECT_SECTION_RESULT not in keep:
            clear_result_selection(state.section_collection)
        if SELECT_CURVE not in keep:
            clear_curve_selection(state.curve_collection)
        if SELECT_SURFACE not in keep:
            clear_surface_selection(state.surface_collection)
            clear_brep_surface_selection(state.brep_surface_collection)
        if SELECT_REGION not in keep:
            region = state.region_collection.active_region
            if region is not None:
                region.selected = False

    def _clear_transform_session(self) -> None:
        self.state.active_transform_mode = None
        self.state.active_transform_axis = None
        self.state.transform_state = None


__all__ = (
    "SELECT_CURVE",
    "SELECT_MODEL",
    "SELECT_REGION",
    "SELECT_SECTION_PLANE",
    "SELECT_SECTION_RESULT",
    "SELECT_SURFACE",
    "SelectionController",
)
