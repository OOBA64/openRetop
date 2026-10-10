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
    {"model.sketch", "model.section_sketch", "model.extrude", "model.fit_surface", "model.loft", "model.fill", "model.extend", "model.trim", "model.compare"}
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
        "model.sketch",
        "model.sketch_options",
        "model.section_fit",
        "model.section_create",
        "model.extrude",
        "model.extrude_preview",
        "model.extrude_apply",
        "model.section_edit",
        "model.edit_feature",
        "model.rebuild",
    }
)
NODE_SKETCH = "sketch_curves"  # the scene tree group of 3D Sketch curves
NODE_HISTORY = "history"  # the scene tree group of the design history (P-01)
FEATURE_PREFIX = "feature:"
SNAP_PIXELS = 10.0  # a click this close to a sketch point (on screen) means that point
TOOL_HINTS = {
    "sketch": "Click points on the scan; Enter finishes. Click a point to select / drag it, double-click a curve to add a point, right-click for more.",
    "extrude": "The depth comes from the scan; adjust ahead / behind / draft, pick New, Add or Cut, then Create (Enter).",
    "section": "Click the scan to move the sketch plane there; Fit Profile. Then drag corners, click a segment to change it (Ctrl+click moves the plane); Create (Enter).",
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
            if result.success and self.modeling.tool == "extrude":
                self._dispatch_application_action("model.extrude_preview")  # type: ignore[attr-defined]  # live
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
        if self._brush_key(key):
            return True
        if key == Qt.Key.Key_Escape:
            self._dispatch_application_action("model.finish")  # type: ignore[attr-defined]
            return True
        session = self.modeling.session
        if (
            self.modeling.tool == "section"
            and key == Qt.Key.Key_Delete
            and session.section_selected is not None
            and session.section_selected[0] == "segment"
        ):
            self._dispatch_application_action("model.section_profile_edit", {"operation": "delete"})  # type: ignore[attr-defined]
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
                "extrude": "model.extrude_apply",
            }.get(self.modeling.tool or "")
            if primary:
                self._dispatch_application_action(primary)  # type: ignore[attr-defined]
                return True
        return False

    def _brush_key(self, key: int) -> bool:
        """[ and ] shrink and grow the brush."""

        session = self.modeling.session
        if session is None or session.tool != "fit_surface" or session.selection_mode not in ("brush", "erase"):
            return False
        if key == Qt.Key.Key_BracketLeft:
            factor = 0.8
        elif key == Qt.Key.Key_BracketRight:
            factor = 1.25
        else:
            return False
        self.modeling.configure(brush_radius=max(1e-4, float(session.brush_radius) * factor))
        self.set_status_message(f"Brush radius {session.brush_radius:.3g} {self.composition.state.units}")  # type: ignore[attr-defined]
        self.refresh()  # type: ignore[attr-defined]
        return True

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
        if key == Qt.Key.Key_Backspace and drawing:
            self._apply_model_result("model.sketch_undo_point", self.modeling.sketch_undo_point())
            return True
        if key == Qt.Key.Key_C and drawing:
            self._apply_model_result("model.sketch_close", self.modeling.sketch_finish(close=True))
            return True
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not drawing and session.selected_node is not None:
            self._dispatch_application_action("model.sketch_delete_point")  # type: ignore[attr-defined]
            return True
        return False

    def _surfacing_press_claim(self, x_position: int, y_position: int) -> bool:
        """The 3D Sketch and the Section Sketch are choosy: they take a press on one of their
        points (to drag it); anywhere else the drag rotates the view and a click still picks."""

        session = self.modeling.session
        if session is not None and session.tool == "section":
            corner = self._section_vertex_at(x_position, y_position)
            self._section_drag = corner
            self._drag_moved = False
            return corner is not None
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
        if session is not None and session.tool == "section" and session.section_profiles is not None:
            return "section"
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
            if event_name in ("motion", "left_press"):  # the ring showing the brush follows the pointer
                hover = self.viewport.pick_mesh(x_position, y_position)
                self._brush_center = np.asarray(hover.position, dtype=float) if hover.hit else None
                if not self._brush_active:
                    self._render_scene()  # type: ignore[attr-defined]
            if event_name == "leave":
                self._brush_center = None
                self._render_scene()  # type: ignore[attr-defined]
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
        if tool == "section":
            self._section_pointer(event_name, x_position, y_position, pick)
            return True
        if event_name != "left_release" or not self.viewport.last_pointer_release_was_click:
            return True  # drags orbit the view; nothing else to do
        if tool == "fit_surface":
            hit = pick if isinstance(pick, MeshPickResult) else self.viewport.pick_mesh(x_position, y_position)
            result = self.modeling.select_at(hit.triangle_index if hit.hit else None)
            self._consume_result("model.pointer", result)  # type: ignore[attr-defined]
            return True
        if tool == "section":
            self._section_pointer(event_name, x_position, y_position, pick)
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

    def _sketch_curve_at(self, x_position: int, y_position: int) -> tuple[str | None, object]:
        """The sketch curve passing within a few pixels of the pointer (and the point of it
        nearest there), measured on screen: a 2-pixel line is hard to hit with a pick ray."""

        best: tuple[float, str | None, object] = (SNAP_PIXELS + 1.0, None, None)
        for curve in self.composition.state.model.sketch.curves:
            line = np.asarray(curve.polyline, dtype=float)
            if not curve.visible or len(line) < 2:
                continue
            try:
                projected = np.asarray(self.viewport.project_points(line), dtype=float).reshape(len(line), -1)
            except Exception:  # viewport not ready
                return None, None
            a, b = projected[:-1, :2], projected[1:, :2]
            pointer = np.array([x_position, y_position], dtype=float)
            span = b - a
            t = np.clip(np.einsum("ij,ij->i", pointer - a, span) / np.maximum(np.einsum("ij,ij->i", span, span), 1e-12), 0.0, 1.0)
            distance = np.linalg.norm(a + span * t[:, None] - pointer, axis=1)
            distance[~np.isfinite(distance)] = np.inf
            index = int(np.argmin(distance))
            if distance[index] < best[0]:
                best = (float(distance[index]), curve.id, line[index] + (line[index + 1] - line[index]) * t[index])
        return best[1], best[2]

    def _sketch_menu(self, x_position: int, y_position: int) -> None:
        """Right click: what can be done to the point or curve under the pointer."""

        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu

        session = self.modeling.session
        model = self.composition.state.model
        node = self._sketch_node_at(x_position, y_position)
        curve_id, position = (None, None) if node is not None else self._sketch_curve_at(x_position, y_position)
        menu = QMenu(self)  # type: ignore[call-overload]
        if node is not None:
            self.modeling.sketch_select_node(node)
            menu.addAction("Delete Point", lambda: self._dispatch_application_action("model.sketch_delete_point", {"node": node}))  # type: ignore[attr-defined]
            menu.addAction("Split Curve Here", lambda: self._dispatch_application_action("model.sketch_split", {"node": node}))  # type: ignore[attr-defined]
            menu.addAction("Start a Curve Here", lambda: self._apply_model_result("model.sketch_click", self.modeling.sketch_click(None, node)))
            curves = tuple(curve.id for curve in model.sketch.curves if node in curve.nodes)
        elif curve_id is not None:
            self.modeling.sketch_select_curves((curve_id,))
            if position is not None:
                point = np.asarray(position, dtype=float).reshape(3).tolist()
                menu.addAction("Add Point Here", lambda: self._dispatch_application_action("model.sketch_insert_point", {"curve": curve_id, "position": point}))  # type: ignore[attr-defined]
            curves = (curve_id,)
        else:
            if session.sketch_points:
                menu.addAction("Finish Curve", lambda: self._apply_model_result("model.sketch_finish", self.modeling.sketch_finish()))
                if len(session.sketch_points) >= 3:
                    menu.addAction("Close Curve", lambda: self._apply_model_result("model.sketch_close", self.modeling.sketch_finish(close=True)))
                menu.addAction("Remove Last Point", lambda: self._apply_model_result("model.sketch_undo_point", self.modeling.sketch_undo_point()))
            curves = ()
        if curves:
            menu.addSeparator()
            menu.addAction("Open / Close Curve", lambda: self._dispatch_application_action("model.sketch_toggle_closed", {"curves": list(curves)}))  # type: ignore[attr-defined]
            menu.addAction("Reverse Curve", lambda: self._dispatch_application_action("model.sketch_reverse", {"curves": list(curves)}))  # type: ignore[attr-defined]
            following = all(getattr(model.sketch.curve(value), "feature", False) for value in curves)
            toggle = menu.addAction("Follow Body Lines")
            toggle.setCheckable(True)
            toggle.setChecked(following)
            toggle.triggered.connect(
                lambda checked: (
                    self.modeling.sketch_select_curves(curves),
                    self._dispatch_application_action("model.sketch_options", {"feature": bool(checked)}),  # type: ignore[attr-defined]
                )
            )
            menu.addAction("Delete Curve", lambda: (self.modeling.sketch_select_curves(curves), self._dispatch_application_action("model.sketch_delete")))  # type: ignore[attr-defined]
        self.refresh()  # type: ignore[attr-defined]
        if not menu.isEmpty():
            self._sketch_last_menu = menu  # for tests
            menu.popup(QCursor.pos())

    _sketch_last_menu: Any = None

    def _sketch_pointer(self, event_name: str, x_position: int, y_position: int) -> None:
        session = self.modeling.session
        if event_name == "right_click":
            self._sketch_menu(x_position, y_position)
            return
        if event_name == "double_click":
            if session.sketch_points:  # the first click placed the point: finish there
                self._apply_model_result("model.sketch_finish", self.modeling.sketch_finish())
                return
            curve_id, position = self._sketch_curve_at(x_position, y_position)
            if curve_id is not None and position is not None:
                point = np.asarray(position, dtype=float).reshape(3).tolist()
                self._dispatch_application_action("model.sketch_insert_point", {"curve": curve_id, "position": point})  # type: ignore[attr-defined]
            return
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
            from PySide6.QtWidgets import QApplication

            control = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
            if session.sketch_points or control:  # connect to it / start a curve from it
                self._apply_model_result("model.sketch_click", self.modeling.sketch_click(None, node))
            else:  # select it for editing
                self._consume_result("model.sketch_select", self.modeling.sketch_select_node(node))  # type: ignore[attr-defined]
            return
        if session.selected_node is not None and not session.sketch_points:
            session.selected_node = None
        if not session.sketch_points:
            # not drawing: a click on a sketch curve selects it (Ctrl adds)
            curve_id, _position = self._sketch_curve_at(x_position, y_position)
            if curve_id is not None:
                from PySide6.QtWidgets import QApplication

                add = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
                result = self.modeling.sketch_select_curves((curve_id,), add=add)
                self._consume_result("model.sketch_select", result)  # type: ignore[attr-defined]
                return
        hit = self.viewport.pick_mesh(x_position, y_position)
        self._apply_model_result("model.sketch_click", self.modeling.sketch_click(hit.position if hit.hit else None))

    _section_drag: tuple[int, int] | None = None

    def _section_vertex_at(self, x_position: int, y_position: int) -> tuple[int, int] | None:
        corners = self.modeling.section_vertices_world()
        if not corners:
            return None
        positions = np.asarray([position for _loop, _index, position in corners], dtype=float)
        try:
            projected = np.asarray(self.viewport.project_points(positions), dtype=float).reshape(len(positions), -1)
        except Exception:  # viewport not ready
            return None
        distance = np.hypot(projected[:, 0] - x_position, projected[:, 1] - y_position)
        distance[~np.isfinite(distance)] = np.inf
        best = int(np.argmin(distance))
        return (corners[best][0], corners[best][1]) if distance[best] <= SNAP_PIXELS else None

    def _section_segment_at(self, x_position: int, y_position: int) -> tuple[int, int] | None:
        pointer = np.array([x_position, y_position], dtype=float)
        best: tuple[float, tuple[int, int] | None] = (SNAP_PIXELS + 1.0, None)
        for loop, index, line in self.modeling.section_segments_world():
            try:
                projected = np.asarray(self.viewport.project_points(line), dtype=float).reshape(len(line), -1)[:, :2]
            except Exception:
                return None
            a, b = projected[:-1], projected[1:]
            span = b - a
            t = np.clip(np.einsum("ij,ij->i", pointer - a, span) / np.maximum(np.einsum("ij,ij->i", span, span), 1e-12), 0.0, 1.0)
            distance = np.linalg.norm(a + span * t[:, None] - pointer, axis=1)
            distance[~np.isfinite(distance)] = np.inf
            if float(distance.min()) < best[0]:
                best = (float(distance.min()), (loop, index))
        return best[1]

    def _section_plane_hit(self, x_position: int, y_position: int) -> np.ndarray | None:
        """Where the line of sight under the pointer meets the sketch plane."""

        frame = self.modeling.section_frame()
        ray = getattr(self.viewport, "pointer_ray", lambda x, y: None)(x_position, y_position)
        if frame is None or ray is None:
            return None
        origin, direction = ray
        normal = np.cross(np.asarray(frame["u"]), np.asarray(frame["v"]))
        facing = float(direction @ normal)
        if abs(facing) < 1e-9:
            return None
        return origin + direction * (float((np.asarray(frame["origin"]) - origin) @ normal) / facing)

    def _section_pointer(self, event_name: str, x_position: int, y_position: int, pick: object) -> None:
        session = self.modeling.session
        if event_name == "right_click":
            self._section_menu(x_position, y_position)
            return
        if event_name == "motion" and self._section_drag is not None:
            point = self._section_plane_hit(x_position, y_position)
            if point is not None:
                self._drag_moved = True
                loop, index = self._section_drag
                self.modeling.section_move_vertex(loop, index, point)
                self._render_scene()  # type: ignore[attr-defined]
            return
        if event_name != "left_release":
            return
        if self._section_drag is not None:
            loop, index = self._section_drag
            self._section_drag = None
            if self._drag_moved:
                self._drag_moved = False
                point = self._section_plane_hit(x_position, y_position)
                if point is not None:
                    self._apply_model_result("model.section_drag", self.modeling.section_move_vertex(loop, index, point, final=True))
                return
            self._consume_result("model.section_select", self.modeling.section_select("vertex", loop, index))  # type: ignore[attr-defined]
            return
        if not self.viewport.last_pointer_release_was_click:
            return  # drags orbit the view
        from PySide6.QtWidgets import QApplication

        control = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ControlModifier)
        if session.section_profiles is not None and not control:
            segment = self._section_segment_at(x_position, y_position)
            result = self.modeling.section_select("segment", *segment) if segment is not None else self.modeling.section_select(None)
            self._consume_result("model.section_select", result)  # type: ignore[attr-defined]
            return
        # no profile yet (or Ctrl+click): move the plane through the point clicked on the scan
        hit = pick if isinstance(pick, MeshPickResult) else self.viewport.pick_mesh(x_position, y_position)
        if hit.hit:
            self._consume_result("model.pointer", self.modeling.section_place(hit.position))  # type: ignore[attr-defined]

    def _section_menu(self, x_position: int, y_position: int) -> None:
        from PySide6.QtGui import QCursor
        from PySide6.QtWidgets import QMenu

        session = self.modeling.session
        if session.section_profiles is None:
            return
        corner = self._section_vertex_at(x_position, y_position)
        segment = None if corner is not None else self._section_segment_at(x_position, y_position)
        if corner is not None:
            self.modeling.section_select("vertex", *corner)
        elif segment is not None:
            self.modeling.section_select("segment", *segment)
        facts = self._section_picked(session)
        menu = QMenu(self)  # type: ignore[call-overload]
        labels = {
            "radius": "Set Radius...",
            "fillet": "Round Corner...",
            "sharp": "Sharp Corner",
            "axis": "Make Horizontal / Vertical",
            "delete": "Delete Segment",
        }
        for operation in ("radius", "fillet", "sharp", "axis", "delete"):
            if operation in facts.get("allowed", ()):
                menu.addAction(labels[operation], lambda operation=operation: self._section_menu_edit(operation))
        if any(not profile.closed for profile in session.section_profiles):
            menu.addAction("Close Profile", lambda: self._dispatch_application_action("model.section_profile_edit", {"operation": "close"}))  # type: ignore[attr-defined]
        self.refresh()  # type: ignore[attr-defined]
        if not menu.isEmpty():
            self._sketch_last_menu = menu
            menu.popup(QCursor.pos())

    def _section_menu_edit(self, operation: str) -> None:
        if operation in ("radius", "fillet"):
            from PySide6.QtWidgets import QInputDialog

            facts = self._section_picked(self.modeling.session)
            value, accepted = QInputDialog.getDouble(
                self, "Radius", "Radius:", float(facts.get("radius") or 1.0), 0.001, 1e5, 3  # type: ignore[arg-type]
            )
            if not accepted:
                return
            self._dispatch_application_action("model.section_profile_edit", {"operation": operation, "value": value})  # type: ignore[attr-defined]
            return
        self._dispatch_application_action("model.section_profile_edit", {"operation": operation})  # type: ignore[attr-defined]

    def _section_picked(self, session: Any) -> dict[str, Any]:
        """What is picked on the profile, and the edits that apply to it."""

        from openretop.modeling import profile_edit

        if session is None or session.section_profiles is None or session.section_selected is None:
            return {}
        kind, loop, index = session.section_selected
        profiles = session.section_profiles
        if loop >= len(profiles) or not profiles[loop].segments:
            return {}
        profile = profiles[loop]
        count = len(profile.segments)
        if kind == "segment":
            if index >= count:
                return {}
            segment = profile.segments[index]
            allowed = ["delete"]
            if segment.kind == "arc":
                allowed.append("radius")
                neighbours = [profile.segments[(index + step) % count] for step in (-1, 1)]
                if (profile.closed or 0 < index < count - 1) and all(item.kind == "line" for item in neighbours):
                    allowed.append("sharp")
            else:
                allowed.append("axis")
            return {
                "text": f"Loop {loop + 1}, segment {index + 1}: {profile_edit.describe(segment)}",
                "radius": segment.radius if segment.kind == "arc" else None,
                "allowed": allowed,
            }
        before = (index - 1) % count if profile.closed else index - 1
        after = index % count if profile.closed else index
        corner = 0 <= before < count and 0 <= after < count and profile.segments[before].kind == profile.segments[after].kind == "line"
        return {
            "text": f"Loop {loop + 1}, corner {index + 1}: drag it to move it" + ("; it can be rounded" if corner else ""),
            "allowed": ["fillet"] if corner else [],
        }

    _dragging = False  # a press landed on a sketch point
    _drag_moved = False  # ... and the pointer moved before release (else it was a click)

    def _fill_pick(self, scene_pick: SceneObjectPickResult, x_position: int, y_position: int) -> None:
        if not scene_pick.hit:
            return
        object_id = str(scene_pick.object_id)
        if object_id.startswith("sketch-curve:"):
            self._consume_result("model.pointer", self.modeling.fill_add_curve(object_id.split(":", 1)[1]))  # type: ignore[attr-defined]
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
        highlight = None
        if section and session.section_selected is not None and session.section_selected[0] == "segment":
            _kind, loop, index = session.section_selected
            highlight = next((line for item_loop, item, line in modeling.section_segments_world() if (item_loop, item) == (loop, index)), None)
        creases = None
        if session is not None and session.tool == "sketch" and session.show_creases:
            creases = modeling.sketch_crease_strength()
        return ModelingSceneInput(
            profile_highlight=highlight,
            creases=creases,
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
        if preview is not None and session.tool == "fit_surface":
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
                curve = model.sketch.curve(side["curve"])
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
            selected_curves=len(model.selected_curve_ids),
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
        if session.tool == "extrude":
            return self._extrude_facts(session)
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
            "selected_node": session.selected_node,
            "feature": all(curve.feature for curve in selected) if selected else bool(session.sketch_feature),
            "smoothness": float(np.mean([curve.smoothness for curve in selected])) if selected else float(session.sketch_smoothness),
            "show_creases": bool(session.show_creases),
        }

    def _extrude_facts(self, session: Any) -> dict[str, Any]:
        model = self.composition.state.model
        units = self.composition.state.units
        profile = model.get(session.extrude_profile)
        target = model.get(session.extrude_target)
        lines = [f"Sketch: {getattr(profile, 'name', 'none')}"]
        if session.extrude_mode != "new":
            lines.append(f"Body: {getattr(target, 'name', 'none')}")
        for index, (low, high) in sorted(session.extrude_holes.items()):
            if session.extrude_auto:
                lines.append(f"Hole {index + 1}: {low:.3f} to {high:.3f} {units} (from the scan)")
        preview = session.preview
        if preview is not None and "volume" in preview:
            lines.append(f"Volume {preview['volume']:.1f} {units}^3" + ("" if preview.get("solid") else " - not a valid solid"))
        return {"extrude_text": "\n".join(lines), "has_target": target is not None}

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
        editing = self.composition.state.model.get(session.section_editing) if session.section_editing else None
        if editing is not None:
            text = f"Editing {editing.name}: Create updates it.\n" + text
        return {
            "loops": loops,
            "section_text": text + tolerance,
            "picked": self._section_picked(session),
            "open_profile": any(not profile.closed for profile in session.section_profiles or ()),
        }

    # -- scene tree ----------------------------------------------------------------------------

    def _surfacing_tool_preview(self) -> Any:
        """The 3D Sketch's points and live curve, drawn by the tool-preview overlay."""

        from openretop.viewer.scene_types import ToolPreviewState, geometry_revision

        session = self.modeling.session
        if session is not None and session.tool == "fit_surface" and session.selection_mode in ("brush", "erase"):
            return self._brush_ring_preview(session)
        if session is not None and session.tool == "section":
            corners = self.modeling.section_vertices_world()
            if not corners:
                return None
            points = np.asarray([position for _loop, _index, position in corners], dtype=float)
            picked = session.section_selected
            highlighted = next(
                (number for number, (loop, index, _p) in enumerate(corners) if picked == ("vertex", loop, index)), None
            )
            return ToolPreviewState(
                revision=geometry_revision(points, highlighted is not None), active=True, node_points=points, highlighted_node_index=highlighted
            )
        if session is None or session.tool != "sketch":
            return None
        sketch = self.composition.state.model.sketch
        ids = list(sketch.nodes)
        nodes = np.asarray([sketch.nodes[node] for node in ids], dtype=float).reshape(-1, 3)
        drawing = np.asarray([position for _node, position in session.sketch_points], dtype=float).reshape(-1, 3)
        line = session.sketch_line if session.sketch_line is not None else np.zeros((0, 3))
        highlighted = ids.index(session.hover_node) if session.hover_node in ids else None
        if highlighted is None and session.selected_node in ids:
            highlighted = ids.index(session.selected_node)
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

    _brush_center: np.ndarray | None = None

    def _brush_ring_preview(self, session: Any) -> Any:
        """A ring the size of the brush around the point under the pointer, facing the view."""

        from openretop.viewer.scene_types import ToolPreviewState, geometry_revision

        center = self._brush_center
        if center is None:
            return None
        view = self._view_direction()
        view = np.array([0.0, 0.0, 1.0]) if view is None else view
        helper = np.array([1.0, 0.0, 0.0]) if abs(view[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
        u = np.cross(view, helper)
        u /= np.linalg.norm(u)
        v = np.cross(view, u)
        angle = np.linspace(0.0, 2.0 * np.pi, 72, endpoint=False)
        radius = float(session.brush_radius)
        ring = center + radius * (np.cos(angle)[:, None] * u + np.sin(angle)[:, None] * v)
        return ToolPreviewState(revision=geometry_revision(ring), active=True, fitted_points=ring, closed=True)

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
        sketch_actions = ("model.section_edit", "model.extrude", "view.frame_selected", "model.delete_selected")
        for entity in model.entities:
            nodes.append(
                SceneNode(
                    model_node_id(entity.id),
                    f"{entity.name}" if entity.label in entity.name else f"{entity.name} ({entity.label})",
                    "model_body" if entity.is_body else "model_surface",
                    NODE_MODEL,
                    entity.visible,
                    metadata={"context_actions": sketch_actions if entity.kind == "profile" else actions},
                )
            )
        features = model.timeline.features
        if features:
            nodes.append(SceneNode(NODE_HISTORY, "History", "group", "scene", metadata={"context_actions": ("model.rebuild",)}, **group))
            nodes.extend(
                SceneNode(
                    f"{FEATURE_PREFIX}{feature.id}",
                    feature.name if feature.status == "ok" else f"{feature.name} ({feature.status})",
                    "feature",
                    NODE_HISTORY,
                    checkable=False,
                    renameable=False,
                    metadata={"context_actions": ("model.rebuild",)},
                )
                for feature in features
            )
        return nodes

    def _surfacing_tree_selection(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        """Take the model rows out of a tree selection (they belong to the model); return the rest."""

        model_ids = tuple(value for value in (model_id_from_node(node) for node in ids) if value is not None)
        curve_ids = tuple(node.split(":", 1)[1] for node in ids if str(node).startswith("sketch:"))
        feature_ids = [node[len(FEATURE_PREFIX) :] for node in ids if str(node).startswith(FEATURE_PREFIX)]
        others = tuple(
            node
            for node in ids
            if model_id_from_node(node) is None and not str(node).startswith(("sketch:", FEATURE_PREFIX)) and node != NODE_HISTORY
        )
        self.modeling.select_entities(model_ids)
        self.modeling.sketch_select_curves(curve_ids)
        self.composition.state.model.selected_feature = feature_ids[0] if feature_ids else ""
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
        feature = (f"{FEATURE_PREFIX}{model.selected_feature}",) if model.timeline.get(model.selected_feature) else ()
        return tuple(model_node_id(value) for value in model.selected_ids) + tuple(f"sketch:{value}" for value in model.selected_curve_ids) + feature

    def _feature_inspector_fields(self, feature_id: str) -> tuple[FieldDefinition, ...] | None:
        """A history feature's inputs; an extrude's can be changed (the rest is rebuilt)."""

        model = self.composition.state.model
        feature = model.timeline.get(feature_id)
        if feature is None:
            return None
        units = self.composition.state.units
        status = "OK" if feature.status == "ok" else f"{feature.status.title()}: {feature.message}"
        fields = [
            FieldDefinition("feature_name", "Feature", feature.name, "readonly", read_only=True),
            FieldDefinition("feature_status", "Status", status, "readonly", read_only=True),
        ]
        inputs = feature.inputs
        if feature.kind == "extrude":
            sketch = model.timeline.get(str(inputs.get("sketch", "")))
            fields.extend(
                (
                    FieldDefinition("feature_sketch", "Sketch", "(deleted)" if sketch is None else sketch.name, "readonly", read_only=True),
                    FieldDefinition("feature_mode", "Operation", str(inputs.get("mode", "new")), "combo", options=("new", "add", "cut"), group="Extrude"),
                    FieldDefinition("feature_front", f"Ahead ({units})", float(inputs.get("front", 0.0)), "number", minimum=0.0, maximum=1e6, group="Extrude"),
                    FieldDefinition("feature_back", f"Behind ({units})", float(inputs.get("back", 0.0)), "number", minimum=0.0, maximum=1e6, group="Extrude"),
                    FieldDefinition("feature_draft", "Draft (degrees)", float(inputs.get("draft", 0.0)), "number", minimum=-45.0, maximum=45.0, group="Extrude"),
                    FieldDefinition("feature_auto", "Hole depths from the scan", bool(inputs.get("auto", True)), "checkbox", group="Extrude"),
                )
            )
        elif feature.kind == "sketch":
            fields.extend(
                (
                    FieldDefinition("feature_plane", "Plane", f"{inputs.get('plane', '?')} at {float(inputs.get('offset', 0.0)):g} {units}", "readonly", read_only=True),
                    FieldDefinition("feature_loops", "Loops", len(inputs.get("loops", [])), "readonly", read_only=True),
                    FieldDefinition("feature_hint", "To change it", "select the sketch under Model, then Edit Sketch", "readonly", read_only=True),
                )
            )
        else:
            fields.append(FieldDefinition("feature_hint", "Body", "kept as it was when first used (no history before it)", "readonly", read_only=True))
        return tuple(fields)

    def _surfacing_inspector_value(self, node_id: str, field_id: str, value: object) -> bool:
        """Edits made in Properties to a history feature: replayed from that feature on."""

        if not str(node_id).startswith(FEATURE_PREFIX) or not field_id.startswith("feature_"):
            return False
        key = field_id[len("feature_") :]
        if key not in {"mode", "front", "back", "draft", "auto"}:
            return True
        cast = {"mode": str, "auto": bool}.get(key, float)
        self._dispatch_application_action("model.edit_feature", {"feature": node_id[len(FEATURE_PREFIX) :], key: cast(value)})  # type: ignore[attr-defined]
        return True

    def _surfacing_inspector_fields(self, node_id: str) -> tuple[FieldDefinition, ...] | None:
        if str(node_id).startswith(FEATURE_PREFIX):
            return self._feature_inspector_fields(node_id[len(FEATURE_PREFIX) :])
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
