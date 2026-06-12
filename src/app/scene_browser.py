"""Scene browser panel for the openRetop main window."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from tkinter import ttk

from app.selection_types import (
    SELECT_CURVE,
    SELECT_MODEL,
    SELECT_SECTION_PLANE,
    SELECT_SURFACE,
)
from curves.curve_state import StoredCurve
from sections.section_state import SectionPlaneState, StoredSectionResult
from surfaces.surface_state import SurfacePatch


NODE_SCENE = "scene"
NODE_MESH = "model"
NODE_SECTION_PLANES = "section_planes"
NODE_SECTION_PLANE = "section_plane"
NODE_SECTION_RESULTS = "section_results"
NODE_SECTION_RESULT = "section_result"
NODE_CURVES = "curves"
NODE_CURVE = "curve"
NODE_SURFACES = "surfaces"
NODE_SURFACE = "surface"


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


class SceneBrowser:
    """Owns the right-side scene hierarchy and selection synchronization."""

    def __init__(
        self,
        parent: ttk.Frame,
        *,
        selection_callback: Callable[[str | None, tuple[str, ...]], None],
    ) -> None:
        self.selection_callback = selection_callback
        self._syncing_selection = False
        self._active_section_plane_node_id: str | None = None
        self._section_plane_node_ids: set[str] = set()
        self._section_result_node_ids: set[str] = set()
        self._curve_node_ids: set[str] = set()
        self._active_curve_node_id: str | None = None
        self._selected_curve_node_ids: set[str] = set()
        self._surface_node_ids: set[str] = set()
        self._active_surface_node_id: str | None = None

        self.frame = ttk.Frame(parent, width=220, padding=(8, 8))
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

        self.tree.insert("", "end", iid=NODE_SCENE, text="Scene", open=True)

    def update_scene(
        self,
        *,
        has_mesh: bool,
        section_planes: Sequence[SectionPlaneState],
        active_section_plane_id: str | None,
        section_results: Sequence[StoredSectionResult],
        curves: Sequence[StoredCurve],
        active_curve_id: str | None,
        selected_curve_ids: set[str],
        surfaces: Sequence[SurfacePatch],
        active_surface_id: str | None,
        has_section_result: bool,
        has_curves: bool,
        has_surfaces: bool,
        selected_item: str | None,
    ) -> None:
        """Refresh visible nodes from app state and mirror viewport selection."""

        has_mesh = bool(has_mesh)
        has_section_result = has_mesh and bool(has_section_result)
        has_curves = has_mesh and bool(has_curves)
        has_surfaces = has_mesh and bool(has_surfaces)

        self._syncing_selection = True
        try:
            if has_mesh:
                self._ensure_node(NODE_MESH, "Mesh")
                self._sync_section_plane_nodes(
                    section_planes,
                    active_section_plane_id=active_section_plane_id,
                )
            else:
                self._remove_node(NODE_MESH)
                self._remove_section_plane_nodes()

            if has_section_result:
                self._sync_section_result_nodes(section_results)
            else:
                self._remove_section_result_nodes()

            if has_curves:
                self._sync_curve_nodes(
                    curves,
                    active_curve_id=active_curve_id,
                    selected_curve_ids=selected_curve_ids,
                )
            else:
                self._remove_curve_nodes()

            if has_surfaces:
                self._sync_surface_nodes(
                    surfaces,
                    active_surface_id=active_surface_id,
                )
            else:
                self._remove_surface_nodes()

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
    ) -> None:
        self._ensure_node(NODE_SECTION_PLANES, "Section Planes", open_node=True)

        current_node_ids: list[str] = []
        for index, plane in enumerate(section_planes, start=1):
            node_id = section_plane_node_id(plane.id)
            current_node_ids.append(node_id)
            label = plane.name or f"Section Plane {index}"
            self._ensure_node(node_id, label, parent=NODE_SECTION_PLANES)

        current_node_id_set = set(current_node_ids)
        for child_id in self.tree.get_children(NODE_SECTION_PLANES):
            if child_id not in current_node_id_set:
                self.tree.delete(child_id)

        self._section_plane_node_ids = current_node_id_set
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
        self._active_section_plane_node_id = None
        self._remove_node(NODE_SECTION_PLANES)

    def _sync_section_result_nodes(
        self,
        section_results: Sequence[StoredSectionResult],
    ) -> None:
        self._ensure_node(NODE_SECTION_RESULTS, "Section Results", open_node=True)

        current_node_ids: list[str] = []
        for index, result in enumerate(section_results, start=1):
            node_id = section_result_node_id(result.id)
            current_node_ids.append(node_id)
            label = result.name or f"Section {index}"
            self._ensure_node(node_id, label, parent=NODE_SECTION_RESULTS)

        current_node_id_set = set(current_node_ids)
        for child_id in self.tree.get_children(NODE_SECTION_RESULTS):
            if child_id not in current_node_id_set:
                self.tree.delete(child_id)

        self._section_result_node_ids = current_node_id_set

    def _remove_section_result_nodes(self) -> None:
        self._section_result_node_ids = set()
        self._remove_node(NODE_SECTION_RESULTS)

    def _sync_curve_nodes(
        self,
        curves: Sequence[StoredCurve],
        *,
        active_curve_id: str | None,
        selected_curve_ids: set[str],
    ) -> None:
        self._ensure_node(NODE_CURVES, "Curves", open_node=True)
        # TODO(task-38): Group curve nodes by section_result_id once the
        # browser supports grouped multi-selection without breaking flat-node
        # keyboard navigation and existing project scene tests.

        current_node_ids: list[str] = []
        for index, curve in enumerate(curves, start=1):
            node_id = curve_node_id(curve.id)
            current_node_ids.append(node_id)
            label = curve.name or f"Curve {index}"
            self._ensure_node(node_id, label, parent=NODE_CURVES)

        current_node_id_set = set(current_node_ids)
        for child_id in self.tree.get_children(NODE_CURVES):
            if child_id not in current_node_id_set:
                self.tree.delete(child_id)

        self._curve_node_ids = current_node_id_set
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

    def _remove_curve_nodes(self) -> None:
        self._curve_node_ids = set()
        self._active_curve_node_id = None
        self._selected_curve_node_ids = set()
        self._remove_node(NODE_CURVES)

    def _sync_surface_nodes(
        self,
        surfaces: Sequence[SurfacePatch],
        *,
        active_surface_id: str | None,
    ) -> None:
        self._ensure_node(NODE_SURFACES, "Surfaces", open_node=True)

        current_node_ids: list[str] = []
        for index, surface in enumerate(surfaces, start=1):
            node_id = surface_node_id(surface.id)
            current_node_ids.append(node_id)
            label = surface.name or f"Surface {index}"
            self._ensure_node(node_id, label, parent=NODE_SURFACES)

        current_node_id_set = set(current_node_ids)
        for child_id in self.tree.get_children(NODE_SURFACES):
            if child_id not in current_node_id_set:
                self.tree.delete(child_id)

        self._surface_node_ids = current_node_id_set
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
        self._active_surface_node_id = None
        self._remove_node(NODE_SURFACES)

    def _remove_node(self, node_id: str) -> None:
        if self.tree.exists(node_id):
            self.tree.delete(node_id)

    def _order_nodes(self) -> None:
        ordered_nodes = (
            NODE_MESH,
            NODE_SECTION_PLANES,
            NODE_SECTION_RESULTS,
            NODE_CURVES,
            NODE_SURFACES,
        )
        for index, node_id in enumerate(ordered_nodes):
            if self.tree.exists(node_id):
                self.tree.move(node_id, NODE_SCENE, index)

    def _sync_tree_selection(self, selected_item: str | None) -> None:
        if selected_item == SELECT_CURVE and self._selected_curve_node_ids:
            node_ids = tuple(
                node_id
                for node_id in self.tree.get_children(NODE_CURVES)
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

        curve_selection = tuple(
            node_id for node_id in selection if node_id in self._curve_node_ids
        )
        if curve_selection and len(curve_selection) == len(selection):
            focused_node = self.tree.focus()
            node_id = focused_node if focused_node in curve_selection else curve_selection[-1]
            self.selection_callback(
                self._selection_for_node(node_id),
                tuple(self._selection_for_node(item) or item for item in curve_selection),
            )
            return

        focused_node = self.tree.focus()
        node_id = focused_node if focused_node in selection else selection[0]
        if len(selection) > 1:
            self._syncing_selection = True
            try:
                self.tree.selection_set(node_id)
            finally:
                self._syncing_selection = False
        selected_item = self._selection_for_node(node_id)
        self.selection_callback(
            selected_item,
            () if selected_item is None else (selected_item,),
        )

    def _node_for_selection(self, selected_item: str | None) -> str | None:
        if selected_item == SELECT_MODEL:
            return NODE_MESH
        if selected_item == SELECT_SECTION_PLANE:
            return self._active_section_plane_node_id
        if selected_item == SELECT_CURVE:
            return self._active_curve_node_id
        if selected_item == SELECT_SURFACE:
            return self._active_surface_node_id
        return None

    def _selection_for_node(self, node_id: str | None) -> str | None:
        if node_id == NODE_MESH:
            return SELECT_MODEL
        if node_id in self._section_plane_node_ids:
            return node_id
        if node_id in self._curve_node_ids:
            return node_id
        if node_id in self._surface_node_ids:
            return node_id
        return None
