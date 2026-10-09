"""Main-window side of the surfacing tools (milestone S).

A mixin for ``OpenRetopV3Window``: the tool panel, the scene tree's Model group, viewport
picks and brush strokes for the tools, the deviation map and model export. The window calls
these hooks from its own refresh, pointer, key and tree handlers.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QVBoxLayout

from openretop.application.modeling_controller import TOOL_TITLES
from openretop.application.results import CommandResult
from openretop.modeling.document import KIND_LABELS
from openretop.presentation.qt.surfacing_panel import PanelFacts, SurfacingPanel
from openretop.viewer.modeling_scene import ModelingSceneInput, model_id_from_node, model_node_id
from openretop.viewer.picking_service import MeshPickResult, SceneObjectPickResult
from workbench_ui import FieldDefinition, SceneNode

NODE_MODEL = "model_surfaces"  # the scene tree group of model surfaces and bodies (NODE_MESH is "model")

SURFACING_ACTIONS = frozenset(
    {"model.sketch", "model.section_sketch", "model.fit_surface", "model.loft", "model.fill", "model.extend", "model.trim", "model.compare"}
)
# kernel work that can take seconds: run off the UI thread
SURFACING_HEAVY_ACTIONS = frozenset(
    {
        "model.fit_preview",
        "model.fit_create",
        "model.loft_apply",
        "model.fill_apply",
        "model.extend_apply",
        "model.trim_compute",
        "model.trim_apply",
        "model.compare_apply",
        "model.sketch_loft",
        "model.sketch_face",
        "model.section_fit",
        "model.section_create",
    }
)
NODE_SKETCH = "sketch_curves"  # the scene tree group of 3D Sketch curves
SNAP_PIXELS = 10.0  # a click this close to a sketch point (on screen) means that point
TOOL_HINTS = {
    "sketch": "Click points on the scan; click a point to connect, the first point to close. Enter finishes, Backspace undoes a point, drag a point to move it.",
    "section": "Click the scan to move the sketch plane there; Fit Profile, then Create (Enter).",
    "fit_surface": "Click a smooth area of the scan (Smart) or drag over it (Brush; Alt+drag rotates). Then Fit and Create.",
    "loft": "Select two or more curves, in order, then Loft.",
    "fill": "Click surface edges and curves around the gap, in order; then Fill.",
    "extend": "Select surfaces in the tree or the scene, set the distance, Extend.",
    "trim": "Automatic Trim, then click pieces to keep or drop them; Apply sews them.",
    "compare": "Compute colours the scan by its distance to the model.",
}


class SurfacingWorkbenchMixin:
    """Expects the window's ``composition``, ``viewport``, ``refresh`` and status helpers."""

    composition: Any
    viewport: Any
    surfacing_panel: SurfacingPanel

    # -- setup ---------------------------------------------------------------------------------

    def _init_surfacing(self, layout: QVBoxLayout) -> None:
        self.surfacing_panel = SurfacingPanel(self)  # type: ignore[arg-type]
        self.surfacing_panel.setVisible(False)
        self.surfacing_panel.action_requested.connect(self._on_surfacing_action)
        self.surfacing_panel.editing_done.connect(self._focus_viewport)
        layout.insertWidget(0, self.surfacing_panel)
        self._brush_active = False
        setter = getattr(self.viewport, "set_left_press_claim", None)
        if setter is not None:
            setter(self._surfacing_press_claim)

    def _focus_viewport(self) -> None:
        interactor = getattr(self.viewport, "interactor", None)
        if interactor is not None:
            interactor.setFocus()

    @property
    def modeling(self) -> Any:
        return self.composition.modeling_controller

    def _apply_model_result(self, action_id: str, result: CommandResult) -> None:
        """A controller call made outside the action dispatcher: record its undo too."""

        if result.success and result.undo_payload is not None and result.changed:
            self.composition.undo.push(result.undo_payload)
        self._consume_result(action_id, result)  # type: ignore[attr-defined]

    def _on_surfacing_action(self, action_id: str, payload: dict[str, Any]) -> None:
        if action_id == "model.configure":
            # option changes repaint only the panel and scene: no undo, no project change
            result = self.modeling.configure(**payload)
            if not result.success:
                self.set_status_message(result.errors[0])  # type: ignore[attr-defined]
            self.refresh()  # type: ignore[attr-defined]
            return
        self._dispatch_application_action(action_id, payload or None)  # type: ignore[attr-defined]

    # -- tool mode -----------------------------------------------------------------------------

    def _surfacing_tool_mode(self, action_id: str, result: CommandResult) -> None:
        if action_id in SURFACING_ACTIONS and result.success:
            tool = self.modeling.tool or ""
            self.tool_modes.enter("modeling", TOOL_HINTS.get(tool, ""))  # type: ignore[attr-defined]
        elif action_id == "model.finish" and result.success:
            self.tool_modes.finish()  # type: ignore[attr-defined]

    def _surfacing_key(self, key: int) -> bool:
        if not self.modeling.active:
            return False
        if self.modeling.tool == "sketch" and self._sketch_key(key):
            return True
        if key == Qt.Key.Key_Escape:
            self._dispatch_application_action("model.finish")  # type: ignore[attr-defined]
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            primary = {
                "fit_surface": "model.fit_create",
                "fill": "model.fill_apply",
                "extend": "model.extend_apply",
                "trim": "model.trim_apply",
                "compare": "model.compare_apply",
                "loft": "model.loft_apply",
                "section": "model.section_create",
            }.get(self.modeling.tool or "")
            if primary:
                self._dispatch_application_action(primary)  # type: ignore[attr-defined]
                return True
        return False

    def _sketch_key(self, key: int) -> bool:
        session = self.modeling.session
        drawing = bool(session.sketch_points)
        if key == Qt.Key.Key_Escape and drawing:
            self.modeling.sketch_cancel()
            self.set_status_message("Curve cancelled (Esc again closes 3D Sketch)")  # type: ignore[attr-defined]
            self.refresh()  # type: ignore[attr-defined]
            return True
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if drawing:
                self._apply_model_result("model.sketch_finish", self.modeling.sketch_finish())
            return True
        if key == Qt.Key.Key_Backspace:
            self._apply_model_result("model.sketch_undo_point", self.modeling.sketch_undo_point())
            return True
        if key == Qt.Key.Key_C and drawing:
            self._apply_model_result("model.sketch_close", self.modeling.sketch_finish(close=True))
            return True
        return False

    def _surfacing_press_claim(self, x_position: int, y_position: int) -> bool:
        """Only the 3D Sketch is choosy: it takes a press on one of its points (to drag it);
        anywhere else the drag rotates the view and a click still places a point."""

        session = self.modeling.session
        if session is None or session.tool != "sketch":
            return True
        node = self._sketch_node_at(x_position, y_position)
        session.drag_node = node
        self._dragging = node is not None
        self._drag_moved = False
        return node is not None

    def _sketch_node_at(self, x_position: int, y_position: int) -> str | None:
        nodes = self.composition.state.model.sketch.nodes
        if not nodes:
            return None
        ids = list(nodes)
        positions = np.asarray([nodes[node] for node in ids], dtype=float)
        try:
            projected = np.asarray(self.viewport.project_points(positions), dtype=float).reshape(len(positions), -1)
        except Exception:  # viewport not ready
            return None
        distance = np.hypot(projected[:, 0] - x_position, projected[:, 1] - y_position)
        # points behind the camera project nowhere useful
        distance[~np.isfinite(distance)] = np.inf
        best = int(np.argmin(distance))
        return ids[best] if distance[best] <= SNAP_PIXELS else None

    def _surfacing_capture_owner(self) -> str | None:
        session = self.modeling.session
        if session is not None and session.tool == "sketch":
            return "sketch"
        if session is not None and session.tool == "fit_surface" and session.selection_mode in ("brush", "erase"):
            return "modeling_brush"
        return None

    # -- viewport ------------------------------------------------------------------------------

    def _surfacing_pointer(self, event_name: str, x_position: int, y_position: int, pick: object) -> bool:
        """Route pointer events to the active surfacing tool; True when consumed."""

        session = self.modeling.session
        if session is None:
            return False
        tool = session.tool
        if tool == "sketch":
            self._sketch_pointer(event_name, x_position, y_position)
            return True
        if tool == "fit_surface" and session.selection_mode in ("brush", "erase"):
            if event_name == "left_press":
                self._brush_active = True
            if event_name in ("left_press", "motion") and self._brush_active:
                hit = self.viewport.pick_mesh(x_position, y_position)
                if hit.hit:
                    result = self.modeling.brush_at(hit.position, view_direction=self._view_direction())
                    self.set_status_message(result.status)  # type: ignore[attr-defined]
                    self._render_scene()  # type: ignore[attr-defined]  # only the 3D view: keep strokes fluid
            if event_name in ("left_release", "leave"):
                self._brush_active = False
                self.refresh()  # type: ignore[attr-defined]
            return True
        if event_name != "left_release" or not self.viewport.last_pointer_release_was_click:
            return True  # drags orbit the view; nothing else to do
        if tool == "fit_surface":
            hit = pick if isinstance(pick, MeshPickResult) else self.viewport.pick_mesh(x_position, y_position)
            result = self.modeling.select_at(hit.triangle_index if hit.hit else None)
            self._consume_result("model.pointer", result)  # type: ignore[attr-defined]
            return True
        if tool == "section":
            hit = pick if isinstance(pick, MeshPickResult) else self.viewport.pick_mesh(x_position, y_position)
            if hit.hit:
                self._consume_result("model.pointer", self.modeling.section_place(hit.position))  # type: ignore[attr-defined]
            return True
        scene_pick = pick if isinstance(pick, SceneObjectPickResult) else self.viewport.pick_scene_object(x_position, y_position)
        if tool == "trim":
            if scene_pick.hit and str(scene_pick.object_id).startswith("trim-piece:"):
                index = int(str(scene_pick.object_id).split(":", 1)[1])
                self._consume_result("model.pointer", self.modeling.trim_toggle(index))  # type: ignore[attr-defined]
            return True
        if tool == "fill":
            self._fill_pick(scene_pick, x_position, y_position)
            return True
        if tool in ("extend", "compare", "loft"):
            return False  # ordinary selection picks
        return True

    def _sketch_pointer(self, event_name: str, x_position: int, y_position: int) -> None:
        session = self.modeling.session
        if event_name == "left_press":
            return  # a claimed press is on a point: the drag follows
        if event_name == "motion":
            hit = self.viewport.pick_mesh(x_position, y_position)
            if session.drag_node is not None and self._dragging:
                if hit.hit:
                    self._drag_moved = True
                    self.modeling.sketch_move_node(session.drag_node, hit.position)
            else:
                node = self._sketch_node_at(x_position, y_position)
                self.modeling.sketch_hover(hit.position if hit.hit else None, node)
            self._render_scene()  # type: ignore[attr-defined]  # the 3D view only: keeps it fluid
            return
        if event_name == "leave":
            self.modeling.sketch_hover(None)
            self._render_scene()  # type: ignore[attr-defined]
            return
        if event_name != "left_release":
            return
        if session.drag_node is not None and self._dragging and self._drag_moved:
            node, session.drag_node = session.drag_node, None
            self._dragging = self._drag_moved = False
            hit = self.viewport.pick_mesh(x_position, y_position)
            position = hit.position if hit.hit else self.composition.state.model.sketch.nodes.get(node)
            self._apply_model_result("model.sketch_move", self.modeling.sketch_move_node(node, position, final=True))
            return
        session.drag_node = None
        self._dragging = self._drag_moved = False
        node = self._sketch_node_at(x_position, y_position)
        if node is not None:
            self._apply_model_result("model.sketch_click", self.modeling.sketch_click(None, node))
            return
        if not session.sketch_points:
            # not drawing: a click on a sketch curve selects it (Ctrl adds)
            scene_pick = self.viewport.pick_scene_object(x_position, y_position)
            object_id = str(scene_pick.object_id or "")
            if scene_pick.hit and object_id.startswith("sketch-curve:"):
                from PySide6.QtWidgets import QApplication

                add = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
                result = self.modeling.sketch_select_curves((object_id.split(":", 1)[1],), add=add)
                self._consume_result("model.sketch_select", result)  # type: ignore[attr-defined]
                return
        hit = self.viewport.pick_mesh(x_position, y_position)
        self._apply_model_result("model.sketch_click", self.modeling.sketch_click(hit.position if hit.hit else None))

    _dragging = False  # a press landed on a sketch point
    _drag_moved = False  # ... and the pointer moved before release (else it was a click)

    def _fill_pick(self, scene_pick: SceneObjectPickResult, x_position: int, y_position: int) -> None:
        if not scene_pick.hit:
            return
        object_type = str(scene_pick.object_type)
        object_id = str(scene_pick.object_id)
        if object_type == "curve":
            self._consume_result("model.pointer", self.modeling.fill_add_curve(object_id))  # type: ignore[attr-defined]
            return
        entity_id = None
        if object_id.startswith("model-edges:") or object_id.startswith("model-face:"):
            entity_id = object_id.split(":", 1)[1]
        entity = None if entity_id is None else self.composition.state.model.get(entity_id)
        if entity is None or scene_pick.position is None:
            return
        # the edge of that surface nearest the picked point
        point = np.asarray(scene_pick.position, dtype=float)
        best, best_distance = None, float("inf")
        for index, polyline in enumerate(entity.edges):
            if len(polyline) == 0:
                continue
            distance = float(np.min(np.linalg.norm(polyline - point, axis=1)))
            if distance < best_distance:
                best, best_distance = index, distance
        if best is not None:
            self._consume_result("model.pointer", self.modeling.fill_add_edge(entity.id, best))  # type: ignore[attr-defined]

    def _view_direction(self) -> np.ndarray | None:
        renderer = getattr(self.viewport, "renderer", None)
        if renderer is None:
            return None
        camera = renderer.GetActiveCamera()
        direction = np.asarray(camera.GetFocalPoint(), dtype=float) - np.asarray(camera.GetPosition(), dtype=float)
        norm = float(np.linalg.norm(direction))
        return None if norm == 0 else direction / norm

    def _modeling_scene_input(self) -> ModelingSceneInput:
        modeling = self.modeling
        session = modeling.session
        selection = modeling.selection() if session is not None and session.tool == "fit_surface" else None
        deviation = modeling.deviation
        chain: tuple[tuple[str, int], ...] = ()
        if session is not None and session.tool == "fill":
            chain = tuple((side["entity"], side["edge"]) for side in session.fill_chain if "entity" in side)
        model = self.composition.state.model
        selected_curves = set(model.selected_curve_ids)
        sketch_curves = tuple(
            (curve.id, curve.polyline, curve.id in selected_curves) for curve in model.sketch.curves if curve.visible
        )
        section = session is not None and session.tool == "section"
        return ModelingSceneInput(
            section_lines=tuple(session.section_loops) if section else (),
            profile_lines=tuple(modeling.section_profile_lines()) if section else (),
            section_plane=modeling.section_plane_outline() if section else None,
            sketch_curves=sketch_curves,
            entities=tuple(self.composition.state.model.entities),
            selected_ids=frozenset(self.composition.state.model.selected_ids),
            selection_mask=None if selection is None else selection.mask,
            selection_revision=0 if selection is None else selection.revision,
            preview=None if session is None else session.preview,
            trim_pieces=None if session is None else session.trim_pieces,
            deviation=None if deviation is None else deviation.distances,
            deviation_tolerance=0.05 if deviation is None else deviation.tolerance,
            chain_edges=chain,
        )

    # -- panel ---------------------------------------------------------------------------------

    def _refresh_surfacing_panel(self) -> bool:
        """Paint the panel; True when a surfacing tool is open (the panel replaces the others)."""

        session = self.modeling.session
        self.surfacing_panel.setVisible(session is not None)
        if session is None:
            return False
        state = self.composition.state
        selection = self.modeling.selection() if session.tool == "fit_surface" else None
        preview = session.preview
        preview_text = ""
        if preview is not None:
            net = f", {preview['control_u']} x {preview['control_v']} net" if preview.get("kind") == "freeform" else ""
            preview_text = (
                f"{KIND_LABELS.get(preview.get('kind', ''), preview.get('kind', ''))}{net}\n"
                f"Deviation RMS {preview['rms']:.3f}, max {preview['max_error']:.3f} {state.units}"
            )
        model = state.model
        selected = [model.get(value) for value in model.selected_ids]
        fill_sides = []
        for side in session.fill_chain:
            if "curve" in side:
                curve = next((item for item in state.curve_collection.curves if item.id == side["curve"]), None)
                fill_sides.append(f"{getattr(curve, 'name', 'curve')} - contact")
            else:
                entity = model.get(side["entity"])
                fill_sides.append(f"Edge {side['edge'] + 1} of {getattr(entity, 'name', '?')} - {side['continuity']}")
        trim_text = ""
        if session.trim_pieces is not None:
            kept = sum(1 for piece in session.trim_pieces if piece["keep"])
            trim_text = f"{len(session.trim_pieces)} pieces, {kept} kept. Click a piece to keep or drop it."
        elif session.tool == "trim":
            trim_text = f"{len(session.trim_sources)} surfaces will be trimmed."
        deviation = self.modeling.deviation
        deviation_text = ""
        if deviation is not None:
            stats = deviation.statistics()
            deviation_text = (
                f"RMS {stats['rms']:.3f}, max {stats['max']:.3f} {state.units}\n"
                f"{100 * stats['within']:.1f}% of the scan within +/-{deviation.tolerance:g}"
            )
        facts = PanelFacts(
            title=TOOL_TITLES.get(session.tool, "Surfacing"),
            units=state.units,
            selected_triangles=0 if selection is None else selection.count,
            preview_text=preview_text,
            selected_curves=len(state.curve_collection.selected_curve_ids),
            selected_surfaces=tuple(entity.name for entity in selected if entity is not None and not entity.is_body),
            fill_sides=tuple(fill_sides),
            trim_text=trim_text,
            has_pieces=session.trim_pieces is not None,
            deviation_text=deviation_text,
            has_deviation=deviation is not None,
            busy=bool(self._executor.busy),  # type: ignore[attr-defined]
            extra=self._sketch_facts(session),
        )
        self.surfacing_panel.show_session(session, facts)
        return True

    def _sketch_facts(self, session: Any) -> dict[str, Any]:
        if session.tool == "section":
            return self._section_facts(session)
        model = self.composition.state.model
        selected = [model.sketch.curve(value) for value in model.selected_curve_ids]
        selected = [curve for curve in selected if curve is not None]
        from openretop.modeling.sketch import boundary_loop

        loop = boundary_loop(model.sketch, [curve.id for curve in selected]) is not None
        return {
            "drawing": len(session.sketch_points),
            "curves": len(model.sketch.curves),
            "selected_curves": len(selected),
            "selected_names": ", ".join(curve.name for curve in selected),
            "loop": loop,
            "fit_to_scan": bool(session.face_fit_to_scan),
        }

    def _section_facts(self, session: Any) -> dict[str, Any]:
        if session.section_key is None:
            self.modeling.section_cut()  # the plane as set when the tool opened
        units = self.composition.state.units
        loops = len(session.section_loops)
        tolerance = ""
        if loops and session.section_tolerance <= 0:
            tolerance = f"\nAuto tolerance: {self.modeling.section_tolerance_in_use():.3f} {units} (about 4x the scan noise)."
        if loops == 0:
            text = "The plane misses the scan: click the scan or change the offset."
        elif session.section_profiles is None:
            text = f"{loops} section loop(s). Fit Profile fits lines and arcs to them."
        else:
            lines = []
            for number, profile in enumerate(session.section_profiles, start=1):
                kinds = [segment.kind for segment in profile.segments]
                radii = sorted({round(segment.radius, 2) for segment in profile.segments if segment.kind == "arc"})
                arcs = f", arcs R{', R'.join(f'{radius:g}' for radius in radii)}" if radii else ""
                lines.append(
                    f"Loop {number} ({'closed' if profile.closed else 'open'}): {kinds.count('line')} lines, "
                    f"{kinds.count('arc')} arcs{arcs}; max {profile.deviation:.3f} {units}"
                )
            text = "\n".join(lines)
        return {"loops": loops, "section_text": text + tolerance}

    # -- scene tree ----------------------------------------------------------------------------

    def _surfacing_tool_preview(self) -> Any:
        """The 3D Sketch's points and live curve, drawn by the tool-preview overlay."""

        from openretop.viewer.scene_types import ToolPreviewState, geometry_revision

        session = self.modeling.session
        if session is None or session.tool != "sketch":
            return None
        sketch = self.composition.state.model.sketch
        ids = list(sketch.nodes)
        nodes = np.asarray([sketch.nodes[node] for node in ids], dtype=float).reshape(-1, 3)
        drawing = np.asarray([position for _node, position in session.sketch_points], dtype=float).reshape(-1, 3)
        line = session.sketch_line if session.sketch_line is not None else np.zeros((0, 3))
        highlighted = ids.index(session.hover_node) if session.hover_node in ids else None
        hover = None if session.hover is None or session.hover_node is not None else (float(session.hover[0]), float(session.hover[1]), float(session.hover[2]))
        return ToolPreviewState(
            revision=geometry_revision(drawing, line, nodes, hover is not None),
            active=True,
            control_points=drawing,
            fitted_points=line,
            preview_point=hover,
            preview_valid=hover is not None and not len(drawing),
            node_points=nodes,
            highlighted_node_index=highlighted,
        )

    def _surfacing_nodes(self) -> list[SceneNode]:
        model = self.composition.state.model
        group = {"checkable": False, "selectable": False, "renameable": False}
        sketch_nodes: list[SceneNode] = []
        if model.sketch.curves:
            sketch_nodes.append(SceneNode(NODE_SKETCH, "3D Sketch", "group", "scene", metadata={"context_actions": ("model.sketch", "model.sketch_face", "model.sketch_loft")}, **group))
            sketch_nodes.extend(
                SceneNode(
                    f"sketch:{curve.id}",
                    f"{curve.name} ({'closed' if curve.closed else 'open'})",
                    "curve",
                    NODE_SKETCH,
                    curve.visible,
                    renameable=False,
                    metadata={"context_actions": ("model.sketch_face", "model.sketch_loft", "model.sketch_delete")},
                )
                for curve in model.sketch.curves
            )
        if not model.entities:
            return sketch_nodes
        nodes = sketch_nodes + [SceneNode(NODE_MODEL, "Model", "group", "scene", metadata={"context_actions": ("model.trim", "model.compare", "file.export_model")}, **group)]
        actions = ("view.frame_selected", "model.extend", "model.delete_selected", "file.export_model")
        for entity in model.entities:
            nodes.append(
                SceneNode(
                    model_node_id(entity.id),
                    f"{entity.name}" if entity.label in entity.name else f"{entity.name} ({entity.label})",
                    "model_body" if entity.is_body else "model_surface",
                    NODE_MODEL,
                    entity.visible,
                    metadata={"context_actions": actions},
                )
            )
        return nodes

    def _surfacing_tree_selection(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        """Take the model rows out of a tree selection (they belong to the model); return the rest."""

        model_ids = tuple(value for value in (model_id_from_node(node) for node in ids) if value is not None)
        curve_ids = tuple(node.split(":", 1)[1] for node in ids if str(node).startswith("sketch:"))
        others = tuple(node for node in ids if model_id_from_node(node) is None and not str(node).startswith("sketch:"))
        self.modeling.select_entities(model_ids)
        self.modeling.sketch_select_curves(curve_ids)
        return others

    def _surfacing_tree_visibility(self, node_id: str, visible: bool) -> bool:
        if str(node_id).startswith("sketch:"):
            curve = self.composition.state.model.sketch.curve(node_id.split(":", 1)[1])
            if curve is not None:
                curve.visible = bool(visible)
                self.composition.state.model.revision += 1
                self.refresh()  # type: ignore[attr-defined]
            return True
        entity_id = model_id_from_node(node_id)
        if entity_id is None:
            return False
        result = self.modeling.set_visible(entity_id, visible)
        if result.undo_payload is not None and result.changed:
            self.composition.undo.push(result.undo_payload)
        self._consume_result("tree.visibility", result)  # type: ignore[attr-defined]
        return True

    def _surfacing_tree_rename(self, node_id: str, name: str) -> bool:
        entity_id = model_id_from_node(node_id)
        if entity_id is None:
            return False
        result = self.modeling.rename(entity_id, name)
        if result.undo_payload is not None and result.changed:
            self.composition.undo.push(result.undo_payload)
        self._consume_result("model.rename", result)  # type: ignore[attr-defined]
        return True

    def _surfacing_selected_nodes(self) -> tuple[str, ...]:
        model = self.composition.state.model
        return tuple(model_node_id(value) for value in model.selected_ids) + tuple(f"sketch:{value}" for value in model.selected_curve_ids)

    def _surfacing_inspector_fields(self, node_id: str) -> tuple[FieldDefinition, ...] | None:
        entity_id = model_id_from_node(node_id)
        entity = None if entity_id is None else self.composition.state.model.get(entity_id)
        if entity is None:
            return None
        units = self.composition.state.units
        stats = entity.stats
        fields = [
            FieldDefinition("name", "Name", entity.name),
            FieldDefinition("model_kind", "Type", entity.label, "readonly", read_only=True),
            FieldDefinition("visible", "Visible", entity.visible, "checkbox"),
        ]
        if "rms" in stats:
            fields.append(FieldDefinition("model_rms", f"Deviation RMS ({units})", round(float(stats["rms"]), 4), "readonly", read_only=True, group="Fit"))
            fields.append(FieldDefinition("model_max", f"Deviation max ({units})", round(float(stats.get("max_error", 0.0)), 4), "readonly", read_only=True, group="Fit"))
        if "control_u" in stats:
            fields.append(FieldDefinition("model_net", "Control net", f"{stats['control_u']} x {stats['control_v']}", "readonly", read_only=True, group="Fit"))
        if "area" in stats:
            fields.append(FieldDefinition("model_area", f"Area ({units}^2)", round(float(stats["area"]), 2), "readonly", read_only=True, group="Geometry"))
        if stats.get("solid"):
            fields.append(FieldDefinition("model_volume", f"Volume ({units}^3)", round(float(stats.get("volume", 0.0)), 2), "readonly", read_only=True, group="Geometry"))
        elif "free_edges" in stats:
            fields.append(FieldDefinition("model_open", "Open edges", int(stats["free_edges"]), "readonly", read_only=True, group="Geometry"))
        return tuple(fields)

    # -- export --------------------------------------------------------------------------------

    def export_model(self) -> bool:
        model = self.composition.state.model
        if not model.entities:
            self._report_error("Nothing to export", "Fit or build surfaces first (Surfacing toolbar).")  # type: ignore[attr-defined]
            return False
        path, chosen = QFileDialog.getSaveFileName(
            self,  # type: ignore[arg-type]
            "Export Model",
            "",
            "STEP files (*.step *.stp);;IGES files (*.iges *.igs)",
        )
        if not path:
            return False
        file_format = "iges" if Path(path).suffix.lower() in (".iges", ".igs") or "IGES" in chosen else "step"

        def work() -> CommandResult:
            return self.modeling.export(path, file_format=file_format)  # type: ignore[no-any-return]

        def done(result: object) -> None:
            self._consume_result("file.export_model", result)  # type: ignore[attr-defined]

        return bool(self._run_background("Exporting model", work, done))  # type: ignore[attr-defined]


__all__ = ("NODE_MODEL", "SURFACING_ACTIONS", "SURFACING_HEAVY_ACTIONS", "SurfacingWorkbenchMixin")
