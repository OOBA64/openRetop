"""Scene browser panel for the openRetop main window."""

from __future__ import annotations

from collections.abc import Callable
from tkinter import ttk

from app.selection_types import SELECT_MODEL, SELECT_SECTION_PLANE


NODE_SCENE = "scene"
NODE_MESH = "model"
NODE_SECTION_PLANE = "section_plane"
NODE_SECTION_RESULTS = "section_results"
NODE_CURVES = "curves"


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
                self._ensure_node(NODE_SECTION_PLANE, "Section Plane")
            else:
                self._remove_node(NODE_MESH)
                self._remove_node(NODE_SECTION_PLANE)

            if has_section_result:
                self._ensure_node(NODE_SECTION_RESULTS, "Section Results")
            else:
                self._remove_node(NODE_SECTION_RESULTS)

            if has_curves:
                self._ensure_node(NODE_CURVES, "Curves")
            else:
                self._remove_node(NODE_CURVES)

            self._order_nodes()
            self._sync_tree_selection(selected_item)
        finally:
            self._syncing_selection = False

    def _ensure_node(self, node_id: str, label: str) -> None:
        if self.tree.exists(node_id):
            self.tree.item(node_id, text=label)
            return

        self.tree.insert(NODE_SCENE, "end", iid=node_id, text=label)

    def _remove_node(self, node_id: str) -> None:
        if self.tree.exists(node_id):
            self.tree.delete(node_id)

    def _order_nodes(self) -> None:
        ordered_nodes = (
            NODE_MESH,
            NODE_SECTION_PLANE,
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

    @staticmethod
    def _node_for_selection(selected_item: str | None) -> str | None:
        if selected_item == SELECT_MODEL:
            return NODE_MESH
        if selected_item == SELECT_SECTION_PLANE:
            return NODE_SECTION_PLANE
        return None

    @staticmethod
    def _selection_for_node(node_id: str | None) -> str | None:
        if node_id == NODE_MESH:
            return SELECT_MODEL
        if node_id == NODE_SECTION_PLANE:
            return SELECT_SECTION_PLANE
        return None
