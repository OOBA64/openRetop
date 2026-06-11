"""Scene browser panel for the openRetop main window."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from tkinter import ttk

from app.selection_types import SELECT_MODEL, SELECT_SECTION_PLANE
from sections.section_state import SectionPlaneState, StoredSectionResult


NODE_SCENE = "scene"
NODE_MESH = "model"
NODE_SECTION_PLANES = "section_planes"
NODE_SECTION_PLANE = "section_plane"
NODE_SECTION_RESULTS = "section_results"
NODE_SECTION_RESULT = "section_result"
NODE_CURVES = "curves"


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


class SceneBrowser:
    """Owns the right-side scene hierarchy and selection synchronization."""

    def __init__(
        self,
        parent: ttk.Frame,
        *,
        selection_callback: Callable[[str | None], None],
    ) -> None:
        self.selection_callback = selection_callback
        self._syncing_selection = False
        self._active_section_plane_node_id: str | None = None
        self._section_plane_node_ids: set[str] = set()
        self._section_result_node_ids: set[str] = set()

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
            selectmode="browse",
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
        has_section_result: bool,
        has_curves: bool,
        selected_item: str | None,
    ) -> None:
        """Refresh visible nodes from app state and mirror viewport selection."""

        has_mesh = bool(has_mesh)
        has_section_result = has_mesh and bool(has_section_result)
        has_curves = has_section_result and bool(has_curves)

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
                self._ensure_node(NODE_CURVES, "Curves")
            else:
                self._remove_node(NODE_CURVES)

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

    def _remove_node(self, node_id: str) -> None:
        if self.tree.exists(node_id):
            self.tree.delete(node_id)

    def _order_nodes(self) -> None:
        ordered_nodes = (
            NODE_MESH,
            NODE_SECTION_PLANES,
            NODE_SECTION_RESULTS,
            NODE_CURVES,
        )
        for index, node_id in enumerate(ordered_nodes):
            if self.tree.exists(node_id):
                self.tree.move(node_id, NODE_SCENE, index)

    def _sync_tree_selection(self, selected_item: str | None) -> None:
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
        node_id = selection[0] if selection else None
        self.selection_callback(self._selection_for_node(node_id))

    def _node_for_selection(self, selected_item: str | None) -> str | None:
        if selected_item == SELECT_MODEL:
            return NODE_MESH
        if selected_item == SELECT_SECTION_PLANE:
            return self._active_section_plane_node_id
        return None

    def _selection_for_node(self, node_id: str | None) -> str | None:
        if node_id == NODE_MESH:
            return SELECT_MODEL
        if node_id in self._section_plane_node_ids:
            return node_id
        return None
