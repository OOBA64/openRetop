"""Scene browser panel for the openRetop main window."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from tkinter import Menu, ttk

from app.selection_types import (
    SELECT_CURVE,
    SELECT_MODEL,
    SELECT_REGION,
    SELECT_SECTION_PLANE,
    SELECT_SECTION_RESULT,
    SELECT_SURFACE,
)
from curves.curve_state import StoredCurve
from curves.curve_state import is_repaired_curve
from curves.manual_curve import is_manual_curve_like
from regions.region_state import RegionSelection
from sections.section_state import SectionPlaneState, StoredSectionResult
from surfaces.surface_state import SurfacePatch


NODE_SCENE = "scene"
NODE_EMPTY_SCENE = "empty_scene"
NODE_MESH = "model"
NODE_SECTION_PLANES = "section_planes"
NODE_SECTION_PLANE = "section_plane"
NODE_SECTION_RESULTS = "section_results"
NODE_SECTION_RESULT = "section_result"
NODE_CURVES = "curves"
NODE_CURVE = "curve"
NODE_CURVE_GROUP = "curve_group"
NODE_CURVE_GROUP_UNASSIGNED = f"{NODE_CURVE_GROUP}:unassigned"
NODE_CURVE_GROUP_PROJECTED = f"{NODE_CURVE_GROUP}:projected"
NODE_CURVE_GROUP_REBUILT = f"{NODE_CURVE_GROUP}:rebuilt"
NODE_CURVE_GROUP_REGION_BOUNDARIES = f"{NODE_CURVE_GROUP}:region_boundaries"
NODE_CURVE_GROUP_REPAIRED = f"{NODE_CURVE_GROUP}:repaired"
NODE_CURVE_GROUP_MANUAL = f"{NODE_CURVE_GROUP}:manual"
CURVE_GROUP_PROJECTED_ID = "__projected_curves__"
CURVE_GROUP_REBUILT_ID = "__rebuilt_curves__"
CURVE_GROUP_REGION_BOUNDARIES_ID = "__region_boundary_curves__"
CURVE_GROUP_REPAIRED_ID = "__repaired_curves__"
CURVE_GROUP_MANUAL_ID = "__manual_curves__"
NODE_SURFACES = "surfaces"
NODE_SURFACE = "surface"
NODE_REGIONS = "regions"
NODE_REGION = "region"


def section_plane_node_id(plane_id: str) -> str:
    """Return the tree node ID for a section plane."""

    return f"{NODE_SECTION_PLANE}:{plane_id}"


def section_plane_id_from_node(node_id: str | None) -> str | None:
    if node_id is None:
        return None

    prefix = f"{NODE_SECTION_PLANE}:"
    if not node_id.startswith(prefix):
        return None

    plane_id = node_id[len(prefix) :]
    return plane_id or None


def section_result_node_id(result_id: str) -> str:
    return f"{NODE_SECTION_RESULT}:{result_id}"


def section_result_id_from_node(node_id: str | None) -> str | None:
    if node_id is None:
        return None

    prefix = f"{NODE_SECTION_RESULT}:"
    if not node_id.startswith(prefix):
        return None

    result_id = node_id[len(prefix) :]
    return result_id or None


def curve_group_node_id(section_result_id: str) -> str:
    return f"{NODE_CURVE_GROUP}:{section_result_id}"


def curve_group_id_from_node(node_id: str | None) -> str | None:
    if node_id is None:
        return None
    if node_id == NODE_CURVE_GROUP_UNASSIGNED:
        return ""
    if node_id == NODE_CURVE_GROUP_PROJECTED:
        return CURVE_GROUP_PROJECTED_ID
    if node_id == NODE_CURVE_GROUP_REBUILT:
        return CURVE_GROUP_REBUILT_ID
    if node_id == NODE_CURVE_GROUP_REGION_BOUNDARIES:
        return CURVE_GROUP_REGION_BOUNDARIES_ID
    if node_id == NODE_CURVE_GROUP_REPAIRED:
        return CURVE_GROUP_REPAIRED_ID
    if node_id == NODE_CURVE_GROUP_MANUAL:
        return CURVE_GROUP_MANUAL_ID

    prefix = f"{NODE_CURVE_GROUP}:"
    if not node_id.startswith(prefix):
        return None

    result_id = node_id[len(prefix) :]
    return result_id or None


def curve_node_id(curve_id: str) -> str:
    return f"{NODE_CURVE}:{curve_id}"


def curve_id_from_node(node_id: str | None) -> str | None:
    if node_id is None:
        return None

    prefix = f"{NODE_CURVE}:"
    if not node_id.startswith(prefix):
        return None

    curve_id = node_id[len(prefix) :]
    return curve_id or None


def surface_node_id(surface_id: str) -> str:
    return f"{NODE_SURFACE}:{surface_id}"


def surface_id_from_node(node_id: str | None) -> str | None:
    if node_id is None:
        return None

    prefix = f"{NODE_SURFACE}:"
    if not node_id.startswith(prefix):
        return None

    surface_id = node_id[len(prefix) :]
    return surface_id or None


def region_node_id(region_id: str) -> str:
    return f"{NODE_REGION}:{region_id}"


def region_id_from_node(node_id: str | None) -> str | None:
    if node_id is None:
        return None

    prefix = f"{NODE_REGION}:"
    if not node_id.startswith(prefix):
        return None

    region_id = node_id[len(prefix) :]
    return region_id or None


def _visibility_label(label: str, visible: bool) -> str:
    return f"[V] {label}" if visible else f"[H] {label}"


def _visibility_group_label(label: str, visible_values: Sequence[bool]) -> str:
    values = [bool(value) for value in visible_values]
    if values and all(values):
        prefix = "[V]"
    elif not values or not any(values):
        prefix = "[H]"
    else:
        prefix = "[M]"
    return f"{prefix} {label}"


def _curve_display_label(curve: StoredCurve, fallback_label: str) -> str:
    label = curve.name or fallback_label
    tags: list[str] = []
    projected_curve = _is_projected_curve(curve)
    rebuilt_curve = _is_rebuilt_curve(curve)
    boundary_curve = _is_region_boundary_curve(curve)
    manual_curve = _is_manual_curve(curve)
    if projected_curve:
        tags.append("projected")
        if _is_mesh_snapped_curve(curve):
            tags.append("mesh")
    elif rebuilt_curve:
        tags.append("rebuilt")
        tags.append(_manual_curve_method_label(curve))
    elif boundary_curve:
        tags.append("boundary")
        tags.append("closed" if bool(curve.is_closed) else "open")
    elif manual_curve:
        tags.append("mesh" if _is_mesh_snapped_curve(curve) else "manual")
        tags.append(_manual_curve_method_label(curve))
    elif is_repaired_curve(curve):
        tags.append("repaired")
    if not manual_curve and not boundary_curve and not rebuilt_curve and curve.is_closed:
        tags.append("closed")
    if not manual_curve and curve.is_tiny_fragment:
        tags.append("tiny")
    tags = list(dict.fromkeys(tags))[:2]
    return f"{label} ({', '.join(tags)})" if tags else label


def _region_display_label(region: RegionSelection, fallback_label: str) -> str:
    label = region.name or fallback_label
    triangle_count = len(region.triangle_indices)
    return f"{label} ({triangle_count:,} tris)"


def _surface_display_label(surface: SurfacePatch, fallback_label: str) -> str:
    label = surface.name or fallback_label
    tag = _surface_preview_tag(surface)
    return f"{label} ({tag})" if tag else label


def _surface_preview_tag(surface: SurfacePatch) -> str:
    metadata = surface.metadata if isinstance(surface.metadata, dict) else {}
    preview_mode = str(metadata.get("preview_mode", "")).strip().lower()
    surface_type = str(surface.surface_type).strip().lower()
    if preview_mode == "closed_curve_fill" or surface_type == "preview_fill":
        return "fill"
    if preview_mode == "two_curve_loft" or surface_type == "preview_loft":
        return "loft"
    if preview_mode == "boundary_patch" or surface_type == "preview_boundary_patch":
        return "boundary patch"
    if preview_mode == "four_curve_patch" or surface_type == "preview_four_curve_patch":
        return "4-curve patch"
    if preview_mode == "curve_network_patch" or surface_type == "preview_curve_network_patch":
        return "network patch"
    return ""


def _is_manual_curve(curve: StoredCurve) -> bool:
    return is_manual_curve_like(curve)


def _is_projected_curve(curve: StoredCurve) -> bool:
    metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    return str(metadata.get("creation_type", "")).strip().lower() == "projected_curve"


def _is_rebuilt_curve(curve: StoredCurve) -> bool:
    metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    return str(metadata.get("creation_type", "")).strip().lower() == "rebuilt_curve"


def _is_region_boundary_curve(curve: StoredCurve) -> bool:
    metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    return (
        str(metadata.get("creation_type", "")).strip().lower() == "region_boundary"
        or "source_region_id" in metadata
    )


def _manual_curve_method_label(curve: StoredCurve) -> str:
    metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    method = str(metadata.get("curve_method", "catmull_rom")).strip().lower()
    return "polyline" if method == "polyline" else "smooth"


def _is_mesh_snapped_curve(curve: StoredCurve) -> bool:
    metadata = curve.metadata if isinstance(curve.metadata, dict) else {}
    return (
        str(metadata.get("creation_type", "")).strip().lower() == "curve_on_mesh"
        or str(metadata.get("snap_mode", "")).strip().lower() == "mesh"
        or bool(metadata.get("snap_to_mesh"))
    )


class SceneBrowser:
    """Owns the right-side scene hierarchy and selection synchronization."""

    def __init__(
        self,
        parent: ttk.Frame,
        *,
        selection_callback: Callable[[str | None, tuple[str, ...]], None],
        visibility_callback: Callable[[str, tuple[str, ...]], None] | None = None,
    ) -> None:
        self.selection_callback = selection_callback
        self.visibility_callback = visibility_callback
        self._syncing_selection = False
        self._active_section_plane_node_id: str | None = None
        self._section_plane_node_ids: set[str] = set()
        self._selected_section_plane_node_ids: set[str] = set()
        self._section_result_node_ids: set[str] = set()
        self._active_section_result_node_id: str | None = None
        self._selected_section_result_node_ids: set[str] = set()
        self._curve_group_node_ids: set[str] = set()
        self._curve_node_ids: set[str] = set()
        self._active_curve_node_id: str | None = None
        self._selected_curve_node_ids: set[str] = set()
        self._surface_node_ids: set[str] = set()
        self._active_surface_node_id: str | None = None
        self._selected_surface_node_ids: set[str] = set()
        self._region_node_ids: set[str] = set()
        self._active_region_node_id: str | None = None
        self._selected_region_node_ids: set[str] = set()

        self.frame = ttk.Frame(parent, width=230, padding=(8, 8), style="Sidebar.TFrame")
        self.frame.grid_propagate(False)
        self.frame.columnconfigure(0, weight=1)
        self.frame.rowconfigure(1, weight=1)

        ttk.Label(
            self.frame,
            text="Scene",
            style="SidebarHeading.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.tree = ttk.Treeview(
            self.frame,
            show="tree",
            selectmode="extended",
            height=12,
        )
        self.tree.grid(row=1, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_selection)
        self.tree.bind("<Button-3>", self._on_tree_context_menu)

        self._context_menu = Menu(self.tree, tearoff=False)
        self._select_menu_index = 0
        self._context_menu.add_command(
            label="Select",
            command=lambda: self._emit_visibility_action("select"),
        )
        self._rename_menu_index = 1
        self._context_menu.add_command(
            label="Rename",
            command=lambda: self._emit_visibility_action("rename"),
        )
        self._select_source_curves_menu_index = 2
        self._context_menu.add_command(
            label="Select Source Curves",
            command=lambda: self._emit_visibility_action("select_source_curves"),
        )
        self._isolate_source_curves_menu_index = 3
        self._context_menu.add_command(
            label="Isolate Source Curves",
            command=lambda: self._emit_visibility_action("isolate_source_curves"),
        )
        self._show_source_curves_menu_index = 4
        self._context_menu.add_command(
            label="Show Source Curves",
            command=lambda: self._emit_visibility_action("show_source_curves"),
        )
        self._frame_source_curves_menu_index = 5
        self._context_menu.add_command(
            label="Frame Source Curves",
            command=lambda: self._emit_visibility_action("frame_source_curves"),
        )
        self._context_menu.add_separator()
        self._toggle_visibility_menu_index = 7
        self._context_menu.add_command(
            label="Toggle Visibility",
            command=lambda: self._emit_visibility_action("toggle_visibility"),
        )
        self._hide_selected_menu_index = 8
        self._context_menu.add_command(
            label="Hide Selected",
            command=lambda: self._emit_visibility_action("hide_selected"),
        )
        self._show_selected_menu_index = 9
        self._context_menu.add_command(
            label="Show Selected",
            command=lambda: self._emit_visibility_action("show_selected"),
        )
        self._isolate_selected_menu_index = 10
        self._context_menu.add_command(
            label="Isolate Selected",
            command=lambda: self._emit_visibility_action("hide_unselected"),
        )
        self._show_all_menu_index = 11
        self._context_menu.add_command(
            label="Show All",
            command=lambda: self._emit_visibility_action("show_all"),
        )
        self._context_menu.add_separator()
        self._delete_selected_menu_index = 13
        self._context_menu.add_command(
            label="Delete Selected",
            command=lambda: self._emit_visibility_action("delete_selected"),
        )
        self._frame_selected_menu_index = 14
        self._context_menu.add_command(
            label="Frame Selected",
            command=lambda: self._emit_visibility_action("frame_selected"),
        )
        self._project_curve_menu_index = 15
        self._context_menu.add_command(
            label="Project Selected Curve to Mesh",
            command=lambda: self._emit_visibility_action("project_curve_to_mesh"),
        )
        self._rebuild_curve_menu_index = 16
        self._context_menu.add_command(
            label="Rebuild Selected Curve",
            command=lambda: self._emit_visibility_action("rebuild_curve"),
        )
        self._extract_region_boundary_menu_index = 17
        self._context_menu.add_command(
            label="Extract Region Boundary",
            command=lambda: self._emit_visibility_action("extract_region_boundary"),
        )

        self.tree.insert("", "end", iid=NODE_SCENE, text="Scene", open=True)

    def update_scene(
        self,
        *,
        has_mesh: bool,
        mesh_name: str | None,
        mesh_visible: bool,
        section_planes: Sequence[SectionPlaneState],
        active_section_plane_id: str | None,
        selected_section_plane_ids: set[str],
        section_results: Sequence[StoredSectionResult],
        active_section_result_id: str | None,
        selected_section_result_ids: set[str],
        curves: Sequence[StoredCurve],
        active_curve_id: str | None,
        selected_curve_ids: set[str],
        surfaces: Sequence[SurfacePatch],
        active_surface_id: str | None,
        selected_surface_ids: set[str],
        has_section_result: bool,
        has_curves: bool,
        has_surfaces: bool,
        selected_item: str | None,
        regions: Sequence[RegionSelection] = (),
        active_region_id: str | None = None,
        selected_region_ids: set[str] | None = None,
    ) -> None:
        """Refresh visible nodes from app state and mirror viewport selection."""

        has_mesh = bool(has_mesh)
        has_section_result = has_mesh and bool(has_section_result)
        has_curves = has_mesh and bool(has_curves)
        has_surfaces = has_mesh and bool(has_surfaces)
        has_regions = has_mesh and bool(regions)
        selected_region_ids = selected_region_ids or set()

        self._syncing_selection = True
        try:
            if has_mesh:
                self._remove_node(NODE_EMPTY_SCENE)
                self._ensure_node(
                    NODE_MESH,
                    _visibility_label(mesh_name or "Mesh", bool(mesh_visible)),
                )
                self._sync_section_plane_nodes(
                    section_planes,
                    active_section_plane_id=active_section_plane_id,
                    selected_section_plane_ids=selected_section_plane_ids,
                )
            else:
                self._remove_node(NODE_MESH)
                self._remove_section_plane_nodes()
                self._ensure_node(
                    NODE_EMPTY_SCENE,
                    "No mesh loaded",
                    open_node=False,
                )

            if has_section_result:
                self._sync_section_result_nodes(
                    section_results,
                    active_section_result_id=active_section_result_id,
                    selected_section_result_ids=selected_section_result_ids,
                )
            else:
                self._remove_section_result_nodes()

            if has_curves:
                self._sync_curve_nodes(
                    curves,
                    section_results=section_results,
                    active_curve_id=active_curve_id,
                    selected_curve_ids=selected_curve_ids,
                )
            else:
                self._remove_curve_nodes()

            if has_surfaces:
                self._sync_surface_nodes(
                    surfaces,
                    active_surface_id=active_surface_id,
                    selected_surface_ids=selected_surface_ids,
                )
            else:
                self._remove_surface_nodes()

            if has_regions:
                self._sync_region_nodes(
                    regions,
                    active_region_id=active_region_id,
                    selected_region_ids=selected_region_ids,
                )
            else:
                self._remove_region_nodes()

            self._order_nodes()
            self._sync_tree_selection(selected_item)
        finally:
            self._syncing_selection = False

    def _ensure_node(
        self,
        node_id: str,
        label: str,
        *,
        parent: str = NODE_SCENE,
        open_node: bool = False,
    ) -> None:
        if self.tree.exists(node_id):
            self.tree.item(node_id, text=label)
            if self.tree.parent(node_id) != parent:
                self.tree.move(node_id, parent, "end")
            if open_node:
                self.tree.item(node_id, open=True)
            return

        self.tree.insert(parent, "end", iid=node_id, text=label, open=open_node)

    def _sync_section_plane_nodes(
        self,
        section_planes: Sequence[SectionPlaneState],
        *,
        active_section_plane_id: str | None,
        selected_section_plane_ids: set[str],
    ) -> None:
        self._ensure_node(
            NODE_SECTION_PLANES,
            _visibility_group_label(
                "Section Planes",
                [plane.visible for plane in section_planes],
            ),
            open_node=True,
        )

        current_node_ids: list[str] = []
        for index, plane in enumerate(section_planes, start=1):
            node_id = section_plane_node_id(plane.id)
            current_node_ids.append(node_id)
            label = _visibility_label(
                plane.name or f"Section Plane {index}",
                bool(plane.visible),
            )
            self._ensure_node(node_id, label, parent=NODE_SECTION_PLANES)

        current_node_id_set = set(current_node_ids)
        for child_id in self.tree.get_children(NODE_SECTION_PLANES):
            if child_id not in current_node_id_set:
                self.tree.delete(child_id)

        self._section_plane_node_ids = current_node_id_set
        self._selected_section_plane_node_ids = {
            section_plane_node_id(plane_id)
            for plane_id in selected_section_plane_ids
            if section_plane_node_id(plane_id) in current_node_id_set
        }
        active_node_id = (
            section_plane_node_id(active_section_plane_id)
            if active_section_plane_id is not None
            else None
        )
        if active_node_id in current_node_id_set:
            self._active_section_plane_node_id = active_node_id
        else:
            self._active_section_plane_node_id = (
                current_node_ids[0] if current_node_ids else None
            )

    def _remove_section_plane_nodes(self) -> None:
        self._section_plane_node_ids = set()
        self._selected_section_plane_node_ids = set()
        self._active_section_plane_node_id = None
        self._remove_node(NODE_SECTION_PLANES)

    def _sync_section_result_nodes(
        self,
        section_results: Sequence[StoredSectionResult],
        *,
        active_section_result_id: str | None,
        selected_section_result_ids: set[str],
    ) -> None:
        self._ensure_node(
            NODE_SECTION_RESULTS,
            _visibility_group_label(
                "Section Results",
                [result.visible for result in section_results],
            ),
            open_node=True,
        )

        current_node_ids: list[str] = []
        for index, result in enumerate(section_results, start=1):
            node_id = section_result_node_id(result.id)
            current_node_ids.append(node_id)
            label = _visibility_label(
                result.name or f"Section {index}",
                bool(result.visible),
            )
            self._ensure_node(node_id, label, parent=NODE_SECTION_RESULTS)

        current_node_id_set = set(current_node_ids)
        for child_id in self.tree.get_children(NODE_SECTION_RESULTS):
            if child_id not in current_node_id_set:
                self.tree.delete(child_id)

        self._section_result_node_ids = current_node_id_set
        self._selected_section_result_node_ids = {
            section_result_node_id(result_id)
            for result_id in selected_section_result_ids
            if section_result_node_id(result_id) in current_node_id_set
        }
        active_node_id = (
            section_result_node_id(active_section_result_id)
            if active_section_result_id is not None
            else None
        )
        if active_node_id in current_node_id_set:
            self._active_section_result_node_id = active_node_id
        else:
            self._active_section_result_node_id = (
                current_node_ids[-1] if current_node_ids else None
            )

    def _remove_section_result_nodes(self) -> None:
        self._section_result_node_ids = set()
        self._selected_section_result_node_ids = set()
        self._active_section_result_node_id = None
        self._remove_node(NODE_SECTION_RESULTS)

    def _sync_curve_nodes(
        self,
        curves: Sequence[StoredCurve],
        *,
        section_results: Sequence[StoredSectionResult],
        active_curve_id: str | None,
        selected_curve_ids: set[str],
    ) -> None:
        self._ensure_node(
            NODE_CURVES,
            _visibility_group_label("Curves", [curve.visible for curve in curves]),
            open_node=True,
        )

        result_by_id = {result.id: result for result in section_results}
        curves_by_result_id: dict[str | None, list[StoredCurve]] = {}
        projected_curves: list[StoredCurve] = []
        rebuilt_curves: list[StoredCurve] = []
        region_boundary_curves: list[StoredCurve] = []
        repaired_curves: list[StoredCurve] = []
        manual_curves: list[StoredCurve] = []
        for curve in curves:
            if _is_projected_curve(curve):
                projected_curves.append(curve)
                continue
            if _is_rebuilt_curve(curve):
                rebuilt_curves.append(curve)
                continue
            if _is_region_boundary_curve(curve):
                region_boundary_curves.append(curve)
                continue
            if _is_manual_curve(curve):
                manual_curves.append(curve)
                continue
            if is_repaired_curve(curve):
                repaired_curves.append(curve)
                continue
            group_key = curve.section_result_id if curve.section_result_id in result_by_id else None
            curves_by_result_id.setdefault(group_key, []).append(curve)

        current_group_ids: list[str] = []
        current_node_ids: list[str] = []
        if projected_curves:
            current_group_ids.append(NODE_CURVE_GROUP_PROJECTED)
            self._ensure_node(
                NODE_CURVE_GROUP_PROJECTED,
                _visibility_group_label(
                    "Projected Curves",
                    [curve.visible for curve in projected_curves],
                ),
                parent=NODE_CURVES,
                open_node=True,
            )
            self._sync_curve_group_nodes(
                NODE_CURVE_GROUP_PROJECTED,
                projected_curves,
                current_node_ids,
            )

        if rebuilt_curves:
            current_group_ids.append(NODE_CURVE_GROUP_REBUILT)
            self._ensure_node(
                NODE_CURVE_GROUP_REBUILT,
                _visibility_group_label(
                    "Rebuilt Curves",
                    [curve.visible for curve in rebuilt_curves],
                ),
                parent=NODE_CURVES,
                open_node=True,
            )
            self._sync_curve_group_nodes(
                NODE_CURVE_GROUP_REBUILT,
                rebuilt_curves,
                current_node_ids,
            )

        if region_boundary_curves:
            current_group_ids.append(NODE_CURVE_GROUP_REGION_BOUNDARIES)
            self._ensure_node(
                NODE_CURVE_GROUP_REGION_BOUNDARIES,
                _visibility_group_label(
                    "Region Boundaries",
                    [curve.visible for curve in region_boundary_curves],
                ),
                parent=NODE_CURVES,
                open_node=True,
            )
            self._sync_curve_group_nodes(
                NODE_CURVE_GROUP_REGION_BOUNDARIES,
                region_boundary_curves,
                current_node_ids,
            )

        if manual_curves:
            current_group_ids.append(NODE_CURVE_GROUP_MANUAL)
            self._ensure_node(
                NODE_CURVE_GROUP_MANUAL,
                _visibility_group_label(
                    "Manual Curves",
                    [curve.visible for curve in manual_curves],
                ),
                parent=NODE_CURVES,
                open_node=True,
            )
            self._sync_curve_group_nodes(
                NODE_CURVE_GROUP_MANUAL,
                manual_curves,
                current_node_ids,
            )

        if repaired_curves:
            current_group_ids.append(NODE_CURVE_GROUP_REPAIRED)
            self._ensure_node(
                NODE_CURVE_GROUP_REPAIRED,
                _visibility_group_label(
                    "Repaired Curves",
                    [curve.visible for curve in repaired_curves],
                ),
                parent=NODE_CURVES,
                open_node=True,
            )
            self._sync_curve_group_nodes(
                NODE_CURVE_GROUP_REPAIRED,
                repaired_curves,
                current_node_ids,
            )

        for result in section_results:
            grouped_curves = curves_by_result_id.get(result.id, [])
            if not grouped_curves:
                continue

            group_id = curve_group_node_id(result.id)
            current_group_ids.append(group_id)
            result_label = result.name or "Section"
            self._ensure_node(
                group_id,
                _visibility_group_label(
                    f"Section: {result_label}",
                    [curve.visible for curve in grouped_curves],
                ),
                parent=NODE_CURVES,
                open_node=True,
            )
            self._sync_curve_group_nodes(group_id, grouped_curves, current_node_ids)

        unassigned_curves = curves_by_result_id.get(None, [])
        if unassigned_curves:
            current_group_ids.append(NODE_CURVE_GROUP_UNASSIGNED)
            self._ensure_node(
                NODE_CURVE_GROUP_UNASSIGNED,
                _visibility_group_label(
                    "Unassigned",
                    [curve.visible for curve in unassigned_curves],
                ),
                parent=NODE_CURVES,
                open_node=True,
            )
            self._sync_curve_group_nodes(
                NODE_CURVE_GROUP_UNASSIGNED,
                unassigned_curves,
                current_node_ids,
            )

        current_node_id_set = set(current_node_ids)
        current_group_id_set = set(current_group_ids)
        self._remove_stale_curve_nodes(
            current_group_ids=current_group_id_set,
            current_node_ids=current_node_id_set,
        )
        for index, group_id in enumerate(current_group_ids):
            if self.tree.exists(group_id):
                self.tree.move(group_id, NODE_CURVES, index)
        self._curve_node_ids = current_node_id_set
        self._curve_group_node_ids = current_group_id_set
        active_node_id = (
            curve_node_id(active_curve_id)
            if active_curve_id is not None
            else None
        )
        if active_node_id in current_node_id_set:
            self._active_curve_node_id = active_node_id
        else:
            self._active_curve_node_id = current_node_ids[0] if current_node_ids else None
        self._selected_curve_node_ids = {
            curve_node_id(curve_id)
            for curve_id in selected_curve_ids
            if curve_node_id(curve_id) in current_node_id_set
        }

    def _sync_curve_group_nodes(
        self,
        group_id: str,
        curves: Sequence[StoredCurve],
        current_node_ids: list[str],
    ) -> None:
        for index, curve in enumerate(curves, start=1):
            node_id = curve_node_id(curve.id)
            current_node_ids.append(node_id)
            label = _visibility_label(
                _curve_display_label(curve, f"Curve {index}"),
                bool(curve.visible),
            )
            self._ensure_node(node_id, label, parent=group_id)
            self.tree.move(node_id, group_id, index - 1)

    def _remove_stale_curve_nodes(
        self,
        *,
        current_group_ids: set[str],
        current_node_ids: set[str],
    ) -> None:
        for child_id in self.tree.get_children(NODE_CURVES):
            if child_id in current_group_ids:
                for grandchild_id in self.tree.get_children(child_id):
                    if grandchild_id not in current_node_ids:
                        self.tree.delete(grandchild_id)
                continue

            if child_id not in current_node_ids:
                self.tree.delete(child_id)

    def _remove_curve_nodes(self) -> None:
        self._curve_node_ids = set()
        self._curve_group_node_ids = set()
        self._active_curve_node_id = None
        self._selected_curve_node_ids = set()
        self._remove_node(NODE_CURVES)

    def _sync_surface_nodes(
        self,
        surfaces: Sequence[SurfacePatch],
        *,
        active_surface_id: str | None,
        selected_surface_ids: set[str],
    ) -> None:
        self._ensure_node(
            NODE_SURFACES,
            _visibility_group_label(
                "Surfaces",
                [surface.visible for surface in surfaces],
            ),
            open_node=True,
        )

        current_node_ids: list[str] = []
        for index, surface in enumerate(surfaces, start=1):
            node_id = surface_node_id(surface.id)
            current_node_ids.append(node_id)
            label = _visibility_label(
                _surface_display_label(surface, f"Surface {index}"),
                bool(surface.visible),
            )
            self._ensure_node(node_id, label, parent=NODE_SURFACES)

        current_node_id_set = set(current_node_ids)
        for child_id in self.tree.get_children(NODE_SURFACES):
            if child_id not in current_node_id_set:
                self.tree.delete(child_id)

        self._surface_node_ids = current_node_id_set
        self._selected_surface_node_ids = {
            surface_node_id(surface_id)
            for surface_id in selected_surface_ids
            if surface_node_id(surface_id) in current_node_id_set
        }
        active_node_id = (
            surface_node_id(active_surface_id)
            if active_surface_id is not None
            else None
        )
        if active_node_id in current_node_id_set:
            self._active_surface_node_id = active_node_id
        else:
            self._active_surface_node_id = (
                current_node_ids[0] if current_node_ids else None
            )

    def _remove_surface_nodes(self) -> None:
        self._surface_node_ids = set()
        self._selected_surface_node_ids = set()
        self._active_surface_node_id = None
        self._remove_node(NODE_SURFACES)

    def _sync_region_nodes(
        self,
        regions: Sequence[RegionSelection],
        *,
        active_region_id: str | None,
        selected_region_ids: set[str],
    ) -> None:
        self._ensure_node(
            NODE_REGIONS,
            _visibility_group_label(
                "Regions",
                [region.visible for region in regions],
            ),
            open_node=True,
        )

        current_node_ids: list[str] = []
        for index, region in enumerate(regions, start=1):
            node_id = region_node_id(region.id)
            current_node_ids.append(node_id)
            label = _visibility_label(
                _region_display_label(region, f"Region {index}"),
                bool(region.visible),
            )
            self._ensure_node(node_id, label, parent=NODE_REGIONS)

        current_node_id_set = set(current_node_ids)
        for child_id in self.tree.get_children(NODE_REGIONS):
            if child_id not in current_node_id_set:
                self.tree.delete(child_id)

        self._region_node_ids = current_node_id_set
        self._selected_region_node_ids = {
            region_node_id(region_id)
            for region_id in selected_region_ids
            if region_node_id(region_id) in current_node_id_set
        }
        active_node_id = (
            region_node_id(active_region_id)
            if active_region_id is not None
            else None
        )
        if active_node_id in current_node_id_set:
            self._active_region_node_id = active_node_id
        else:
            self._active_region_node_id = current_node_ids[0] if current_node_ids else None

    def _remove_region_nodes(self) -> None:
        self._region_node_ids = set()
        self._selected_region_node_ids = set()
        self._active_region_node_id = None
        self._remove_node(NODE_REGIONS)

    def _remove_node(self, node_id: str) -> None:
        if self.tree.exists(node_id):
            self.tree.delete(node_id)

    def _order_nodes(self) -> None:
        ordered_nodes = (
            NODE_EMPTY_SCENE,
            NODE_MESH,
            NODE_SECTION_PLANES,
            NODE_SECTION_RESULTS,
            NODE_CURVES,
            NODE_SURFACES,
            NODE_REGIONS,
        )
        for index, node_id in enumerate(ordered_nodes):
            if self.tree.exists(node_id):
                self.tree.move(node_id, NODE_SCENE, index)

    def _sync_tree_selection(self, selected_item: str | None) -> None:
        selected_node_ids = self._selected_node_ids_for_selection(selected_item)
        if selected_node_ids:
            node_ids = tuple(
                node_id
                for node_id in self._node_order()
                if node_id in selected_node_ids and self.tree.exists(node_id)
            )
            if node_ids and self.tree.selection() != node_ids:
                self.tree.selection_set(node_ids)
            focus_node = self._node_for_selection(selected_item)
            if focus_node is not None and self.tree.exists(focus_node):
                self.tree.see(focus_node)
            elif node_ids:
                self.tree.see(node_ids[0])
            return

        if selected_item == SELECT_CURVE and self._selected_curve_node_ids:
            node_ids = tuple(
                node_id
                for node_id in self._curve_node_order()
                if node_id in self._selected_curve_node_ids
            )
            if node_ids and self.tree.selection() != node_ids:
                self.tree.selection_set(node_ids)
            if self._active_curve_node_id is not None and self.tree.exists(
                self._active_curve_node_id
            ):
                self.tree.see(self._active_curve_node_id)
            elif node_ids:
                self.tree.see(node_ids[0])
            return

        node_id = self._node_for_selection(selected_item)
        if node_id is not None and self.tree.exists(node_id):
            if self.tree.selection() != (node_id,):
                self.tree.selection_set(node_id)
            self.tree.see(node_id)
            return

        current_selection = self.tree.selection()
        if current_selection:
            self.tree.selection_remove(current_selection)

    def _on_tree_selection(self, _event: object | None = None) -> None:
        if self._syncing_selection:
            return

        selection = self.tree.selection()
        if not selection:
            self.selection_callback(None, ())
            return

        focused_node = self.tree.focus()
        node_id = focused_node if focused_node in selection else selection[0]
        selected_item = self._selection_for_node(node_id)
        self.selection_callback(
            selected_item,
            tuple(self._selection_for_node(item) or item for item in selection),
        )

    def _node_for_selection(self, selected_item: str | None) -> str | None:
        if selected_item == SELECT_MODEL:
            return NODE_MESH
        if selected_item == SELECT_SECTION_PLANE:
            return self._active_section_plane_node_id
        if selected_item == SELECT_SECTION_RESULT:
            return self._active_section_result_node_id
        if selected_item == SELECT_CURVE:
            return self._active_curve_node_id
        if selected_item == SELECT_SURFACE:
            return self._active_surface_node_id
        if selected_item == SELECT_REGION:
            return self._active_region_node_id
        return None

    def _selection_for_node(self, node_id: str | None) -> str | None:
        if node_id == NODE_MESH:
            return SELECT_MODEL
        if node_id in {
            NODE_SECTION_PLANES,
            NODE_SECTION_RESULTS,
            NODE_CURVES,
            NODE_SURFACES,
            NODE_REGIONS,
        }:
            return node_id
        if node_id in self._curve_group_node_ids:
            return node_id
        if node_id in self._section_plane_node_ids:
            return node_id
        if node_id in self._section_result_node_ids:
            return node_id
        if node_id in self._curve_node_ids:
            return node_id
        if node_id in self._surface_node_ids:
            return node_id
        if node_id in self._region_node_ids:
            return node_id
        return None

    def selected_node_ids(self) -> tuple[str, ...]:
        return tuple(self.tree.selection())

    def _selected_node_ids_for_selection(self, selected_item: str | None) -> set[str]:
        if selected_item == SELECT_SECTION_PLANE:
            return set(self._selected_section_plane_node_ids)
        if selected_item == SELECT_SECTION_RESULT:
            return set(self._selected_section_result_node_ids)
        if selected_item == SELECT_CURVE:
            return set(self._selected_curve_node_ids)
        if selected_item == SELECT_SURFACE:
            return set(self._selected_surface_node_ids)
        if selected_item == SELECT_REGION:
            return set(self._selected_region_node_ids)
        return set()

    def _node_order(self) -> tuple[str, ...]:
        ordered_node_ids: list[str] = []
        for root_node_id in (
            NODE_MESH,
            NODE_SECTION_PLANES,
            NODE_SECTION_RESULTS,
            NODE_CURVES,
            NODE_SURFACES,
            NODE_REGIONS,
        ):
            if not self.tree.exists(root_node_id):
                continue
            ordered_node_ids.append(root_node_id)
            ordered_node_ids.extend(self._descendant_node_ids(root_node_id))
        return tuple(ordered_node_ids)

    def _descendant_node_ids(self, node_id: str) -> tuple[str, ...]:
        descendants: list[str] = []
        for child_id in self.tree.get_children(node_id):
            descendants.append(child_id)
            descendants.extend(self._descendant_node_ids(child_id))
        return tuple(descendants)

    def _curve_node_order(self) -> tuple[str, ...]:
        if not self.tree.exists(NODE_CURVES):
            return ()

        ordered_node_ids: list[str] = []
        for child_id in self.tree.get_children(NODE_CURVES):
            if child_id in self._curve_node_ids:
                ordered_node_ids.append(child_id)
                continue
            ordered_node_ids.extend(
                grandchild_id
                for grandchild_id in self.tree.get_children(child_id)
                if grandchild_id in self._curve_node_ids
            )
        return tuple(ordered_node_ids)

    def _on_tree_context_menu(self, event: object) -> str:
        row_id = self.tree.identify_row(getattr(event, "y", 0))
        if row_id:
            if row_id not in self.tree.selection():
                self.tree.selection_set(row_id)
            self.tree.focus(row_id)

        if self.visibility_callback is not None:
            rename_state = (
                "normal"
                if len(self.selected_node_ids()) == 1
                and self._is_renameable_node(self.selected_node_ids()[0])
                else "disabled"
            )
            source_curve_state = (
                "normal"
                if len(self.selected_node_ids()) == 1
                and surface_id_from_node(self.selected_node_ids()[0]) is not None
                else "disabled"
            )
            selected_node_ids = self.selected_node_ids()
            selected_state = "normal" if selected_node_ids else "disabled"
            region_parent_selected = NODE_REGIONS in selected_node_ids
            region_selected = region_parent_selected or any(
                node_id in self._region_node_ids for node_id in selected_node_ids
            )
            curve_selected = any(
                node_id in self._curve_node_ids or node_id in self._curve_group_node_ids
                for node_id in selected_node_ids
            )
            self._context_menu.entryconfigure(
                self._select_menu_index,
                state=selected_state,
            )
            self._context_menu.entryconfigure(
                self._rename_menu_index,
                state=rename_state,
            )
            self._context_menu.entryconfigure(
                self._select_source_curves_menu_index,
                state=source_curve_state,
            )
            self._context_menu.entryconfigure(
                self._isolate_source_curves_menu_index,
                state=source_curve_state,
            )
            self._context_menu.entryconfigure(
                self._show_source_curves_menu_index,
                state=source_curve_state,
            )
            self._context_menu.entryconfigure(
                self._frame_source_curves_menu_index,
                state=source_curve_state,
            )
            self._context_menu.entryconfigure(
                self._project_curve_menu_index,
                state="normal" if curve_selected else "disabled",
            )
            self._context_menu.entryconfigure(
                self._rebuild_curve_menu_index,
                state="normal" if curve_selected else "disabled",
            )
            self._context_menu.entryconfigure(
                self._hide_selected_menu_index,
                label="Hide Children" if region_parent_selected else "Hide Selected",
            )
            self._context_menu.entryconfigure(
                self._show_selected_menu_index,
                label="Show Children" if region_parent_selected else "Show Selected",
            )
            self._context_menu.entryconfigure(
                self._delete_selected_menu_index,
                label="Delete Children" if region_parent_selected else "Delete Selected",
            )
            self._context_menu.entryconfigure(
                self._extract_region_boundary_menu_index,
                state="normal" if region_selected else "disabled",
            )
            try:
                self._context_menu.tk_popup(
                    getattr(event, "x_root", 0),
                    getattr(event, "y_root", 0),
                )
            finally:
                self._context_menu.grab_release()
        return "break"

    def _is_renameable_node(self, node_id: str) -> bool:
        return (
            node_id == NODE_MESH
            or node_id in self._section_plane_node_ids
            or node_id in self._section_result_node_ids
            or node_id in self._curve_node_ids
            or node_id in self._surface_node_ids
            or node_id in self._region_node_ids
        )

    def _emit_visibility_action(self, action: str) -> None:
        if self.visibility_callback is None:
            return

        self.visibility_callback(action, self.selected_node_ids())
