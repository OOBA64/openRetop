"""The surfacing tools (milestone S): Fit Surface, Loft, Fill, Extend, Trim, Compare, Export.

Each tool is a session: ``start`` it, adjust it (selection, options, picks), ``apply`` it.
Geometry is made by the kernel worker (``cad_kernel.jobs``), so a kernel crash or hang comes
back as a failed ``CommandResult``. New entities go into ``state.model`` with an undo entry.

Coordinates: the selection lives on the display mesh in its own (object) coordinates, like
the scan actor; everything sent to the kernel is in world coordinates, so the surfaces line
up with the scan as shown and export where they appear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from openretop.application.controller_support import CallbackUndoPayload, ControllerBase
from openretop.application.events import EventPublisher
from openretop.application.results import CommandResult
from openretop.application.state import AppState
from openretop.cad_kernel.worker import KernelReply, KernelWorker
from openretop.modeling import (
    DEFAULT_SMART_ANGLE,
    ModelEntity,
    ScanSelection,
    SourceMapping,
    entity_from_result,
    selected_patch,
)

TOOLS = ("fit_surface", "loft", "fill", "extend", "trim", "compare")
TOOL_TITLES = {
    "fit_surface": "Fit Surface",
    "loft": "Loft",
    "fill": "Fill Surface",
    "extend": "Extend Surface",
    "trim": "Trim Surfaces",
    "compare": "Compare",
}
SELECTION_MODES = ("smart", "brush", "erase")
MAX_KERNEL_SCAN_POINTS = 200_000  # scan points sent for trimming (a dense scan is subsampled)


@dataclass
class FitOptions:
    kind: str = "auto"
    control_u: int = 0  # 0 = automatic net
    control_v: int = 0
    smoothness: float = 0.25
    expand: float = 0.15
    tolerance: float = 0.05


@dataclass
class ToolSession:
    tool: str
    selection_mode: str = "smart"
    smart_angle: float = DEFAULT_SMART_ANGLE
    connected: bool = False
    brush_radius: float = 0.0  # world units; 0 until a scan sets a sensible default
    fit: FitOptions = field(default_factory=FitOptions)
    preview: dict[str, Any] | None = None  # a fit result not yet created
    fill_chain: list[dict[str, Any]] = field(default_factory=list)
    fill_on_scan: bool = True
    extend_distance: float = 5.0
    trim_tolerance: float = 0.1
    trim_overlap: float = 0.3
    trim_sources: tuple[str, ...] = ()
    trim_pieces: list[dict[str, Any]] | None = None
    sew_tolerance: float = 0.05


@dataclass
class Deviation:
    distances: np.ndarray  # signed, per display-mesh vertex
    tolerance: float
    entity_ids: tuple[str, ...]

    def statistics(self) -> dict[str, float]:
        finite = self.distances[np.isfinite(self.distances)]
        if len(finite) == 0:
            return {"rms": float("nan"), "max": float("nan"), "within": 0.0}
        return {
            "rms": float(np.sqrt(np.mean(finite**2))),
            "max": float(np.max(np.abs(finite))),
            "mean": float(np.mean(finite)),
            "within": float(np.mean(np.abs(finite) <= self.tolerance)),
        }


class ModelingController(ControllerBase):
    def __init__(
        self,
        state: AppState,
        *,
        transform: Any,
        worker: KernelWorker | None = None,
        events: EventPublisher | None = None,
    ) -> None:
        super().__init__(state, events)
        self.transform = transform  # TransformController: object matrix, world-space source mesh
        self.worker = worker or KernelWorker()
        self.session: ToolSession | None = None
        self.deviation: Deviation | None = None
        self._selection: ScanSelection | None = None
        self._mapping: tuple[tuple[object, object], SourceMapping] | None = None

    def reset(self) -> None:
        """A new project: no tool, no selection, no deviation map."""

        self.session = None
        self.deviation = None
        self._selection = None
        self._mapping = None

    # -- tool sessions -----------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.session is not None

    @property
    def tool(self) -> str | None:
        return None if self.session is None else self.session.tool

    def start(self, tool: str) -> CommandResult:
        if tool not in TOOLS:
            return CommandResult.failure(f"Unknown tool: {tool}")
        if tool in ("fit_surface", "trim", "compare") and self.state.mesh_object is None:
            return CommandResult.failure("Open a scan first (File > Open Model).")
        previous = self.session
        self.session = ToolSession(tool)
        if previous is not None:  # keep the settings a user has dialled in across tools
            self.session.fit = previous.fit
            self.session.selection_mode = previous.selection_mode
            self.session.smart_angle = previous.smart_angle
            self.session.brush_radius = previous.brush_radius
        if self.session.brush_radius <= 0.0:
            self.session.brush_radius = self._default_brush_radius()
        if tool == "trim":
            self.session.trim_sources = tuple(entity.id for entity in self.state.model.visible() if not entity.is_body)
        hints = {
            "fit_surface": "Click the scan to select a smooth area (or brush it), then Fit.",
            "loft": "Select two or more curves, then Loft.",
            "fill": "Click curves or surface edges around the gap, in order; then Fill.",
            "extend": "Select a surface, set the distance, then Extend.",
            "trim": "Trim splits the surfaces by each other and keeps what lies on the scan.",
            "compare": "Compare colours the scan by its distance to the model.",
        }
        return CommandResult.ok(status=f"{TOOL_TITLES[tool]}: {hints[tool]}", changed=True, metadata={"tool": tool})

    def finish(self) -> CommandResult:
        tool = self.tool
        self.session = None
        return CommandResult.ok(status=f"{TOOL_TITLES.get(tool or '', 'Tool')} closed", changed=True)

    def configure(self, **values: Any) -> CommandResult:
        """Change tool options: selection_mode, smart_angle, connected, brush_radius, fit_*,
        fill_on_scan, extend_distance, trim_tolerance, trim_overlap, sew_tolerance."""

        session = self.session
        if session is None:
            return CommandResult.failure("No surfacing tool is active.")
        for key, value in values.items():
            if key.startswith("fit_") and hasattr(session.fit, key[4:]):
                setattr(session.fit, key[4:], type(getattr(session.fit, key[4:]))(value))
            elif hasattr(session, key) and key not in ("tool", "fit", "preview", "trim_pieces", "fill_chain"):
                current = getattr(session, key)
                setattr(session, key, type(current)(value) if current is not None else value)
            else:
                return CommandResult.failure(f"Unknown option: {key}")
        if values.get("selection_mode") is not None and session.selection_mode not in SELECTION_MODES:
            session.selection_mode = "smart"
        return CommandResult.ok(status="Options updated", changed=True)

    # -- scan selection (Fit Surface) ----------------------------------------------------------

    def selection(self) -> ScanSelection | None:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            self._selection = None
            return None
        display = mesh_object.display_mesh
        if self._selection is None or not self._selection.matches(display.vertices, display.triangles):
            self._selection = ScanSelection(display.vertices, display.triangles)
        return self._selection

    def select_at(self, triangle: int | None, *, add: bool | None = None) -> CommandResult:
        session = self.session
        selection = self.selection()
        if session is None or selection is None:
            return CommandResult.failure("Start Fit Surface first.")
        if triangle is None:
            return CommandResult.ok(status="Click on the scan to select an area.")
        adding = session.selection_mode != "erase" if add is None else add
        reached = selection.smart_select(int(triangle), session.smart_angle, add=adding, connected=session.connected)
        session.preview = None
        verb = "Added" if adding else "Removed"
        return CommandResult.ok(status=f"{verb} {reached:,} triangles; {selection.count:,} selected", changed=True)

    def brush_at(self, world_point: object, *, add: bool | None = None, view_direction: object | None = None) -> CommandResult:
        session = self.session
        selection = self.selection()
        if session is None or selection is None or world_point is None:
            return CommandResult.ok()
        matrix = self.transform.current_object_matrix()
        inverse = np.linalg.inv(matrix)
        local = inverse[:3, :3] @ np.asarray(world_point, dtype=float) + inverse[:3, 3]
        scale = float(np.cbrt(abs(np.linalg.det(matrix[:3, :3])))) or 1.0
        direction = None
        if view_direction is not None:
            direction = inverse[:3, :3] @ np.asarray(view_direction, dtype=float)
            direction /= max(float(np.linalg.norm(direction)), 1e-12)
        adding = session.selection_mode != "erase" if add is None else add
        selection.brush(local, session.brush_radius / scale, add=adding, view_direction=direction)
        session.preview = None
        return CommandResult.ok(status=f"{selection.count:,} triangles selected", changed=True)

    def clear_selection(self) -> CommandResult:
        selection = self.selection()
        if selection is not None:
            selection.clear()
        if self.session is not None:
            self.session.preview = None
        return CommandResult.ok(status="Selection cleared", changed=True)

    def invert_selection(self) -> CommandResult:
        selection = self.selection()
        if selection is not None:
            selection.invert()
        if self.session is not None:
            self.session.preview = None
        return CommandResult.ok(status="Selection inverted", changed=True)

    # -- Fit Surface ---------------------------------------------------------------------------

    def fit_preview(self) -> CommandResult:
        session = self.session
        selection = self.selection()
        if session is None or session.tool != "fit_surface":
            return CommandResult.failure("Start Fit Surface first.")
        if selection is None or selection.count == 0:
            return CommandResult.failure("Select an area of the scan first: click it, or brush over it.")
        points, triangles, normals = self._selected_scan_data(selection.mask)
        if len(points) < 12:
            return CommandResult.failure("The selected area is too small to fit.")
        options = session.fit
        reply = self.worker.call(
            "fit_surface",
            points,
            triangles,
            normals,
            kind=options.kind,
            control_u=options.control_u,
            control_v=options.control_v,
            smoothness=options.smoothness,
            expand=options.expand,
            tolerance=options.tolerance,
        )
        if not reply.ok:
            return _kernel_failure("Fit failed", reply)
        session.preview = reply.value
        session.preview["selection_revision"] = selection.revision
        result = reply.value
        net = f", {result['control_u']} x {result['control_v']} net" if result["kind"] == "freeform" else ""
        return CommandResult.ok(
            status=f"{result['kind'].title()}{net}: deviation RMS {result['rms']:.3f}, max {result['max_error']:.3f} "
            f"{self.state.units} ({reply.seconds:.1f} s). Create keeps it.",
            changed=True,
        )

    def create_from_preview(self) -> CommandResult:
        session = self.session
        if session is None or session.preview is None:
            preview = self.fit_preview()
            if not preview.success:
                return preview
            session = self.session
            assert session is not None and session.preview is not None
        result = session.preview
        selection = self.selection()
        params = {
            "kind": session.fit.kind,
            "control_u": session.fit.control_u,
            "control_v": session.fit.control_v,
            "smoothness": session.fit.smoothness,
            "expand": session.fit.expand,
            "triangles": [] if selection is None else selection.triangle_indices().tolist(),
        }
        entity = entity_from_result(self.state.model, result, tool="fit_surface", params=params)
        outcome = self._add_entities([entity], name=f"Fit {entity.label}")
        session.preview = None
        if selection is not None:
            selection.clear()
        return outcome

    # -- Loft ----------------------------------------------------------------------------------

    def loft(self, curve_ids: tuple[str, ...] | None = None, *, ruled: bool = False) -> CommandResult:
        ids = curve_ids if curve_ids is not None else tuple(self.state.curve_collection.selected_curve_ids)
        curves = [curve for curve in self.state.curve_collection.curves if curve.id in set(ids)]
        if len(curves) < 2:
            return CommandResult.failure("Select two or more curves to loft between (Ctrl+click in the tree or scene).")
        order = {curve_id: index for index, curve_id in enumerate(ids)}
        curves.sort(key=lambda curve: order.get(curve.id, 0))
        polylines = [_curve_points(curve) for curve in curves]
        reply = self.worker.call("loft", polylines, ruled=ruled)
        if not reply.ok:
            return _kernel_failure("Loft failed", reply)
        entity = entity_from_result(self.state.model, reply.value, tool="loft", params={"curves": [curve.id for curve in curves], "ruled": ruled})
        return self._add_entities([entity], name="Loft")

    # -- Fill ----------------------------------------------------------------------------------

    def fill_add_edge(self, entity_id: str, edge: int) -> CommandResult:
        session = self._session_for("fill")
        if isinstance(session, CommandResult):
            return session
        entity = self.state.model.get(entity_id)
        if entity is None or not 0 <= edge < len(entity.edges):
            return CommandResult.failure("Pick an edge of a surface.")
        session.fill_chain.append({"entity": entity_id, "edge": int(edge), "continuity": "smooth"})
        return CommandResult.ok(status=f"Boundary: {len(session.fill_chain)} sides", changed=True)

    def fill_add_curve(self, curve_id: str) -> CommandResult:
        session = self._session_for("fill")
        if isinstance(session, CommandResult):
            return session
        if not any(curve.id == curve_id for curve in self.state.curve_collection.curves):
            return CommandResult.failure("Pick a curve.")
        session.fill_chain.append({"curve": curve_id, "continuity": "contact"})
        return CommandResult.ok(status=f"Boundary: {len(session.fill_chain)} sides", changed=True)

    def fill_set_continuity(self, index: int, continuity: str) -> CommandResult:
        session = self._session_for("fill")
        if isinstance(session, CommandResult):
            return session
        if not 0 <= index < len(session.fill_chain) or continuity not in ("contact", "smooth"):
            return CommandResult.failure("No such boundary side.")
        if continuity == "smooth" and "entity" not in session.fill_chain[index]:
            return CommandResult.failure("Smooth needs a surface edge (a curve has no tangent plane).")
        session.fill_chain[index]["continuity"] = continuity
        return CommandResult.ok(status="Continuity changed", changed=True)

    def fill_clear(self) -> CommandResult:
        session = self._session_for("fill")
        if isinstance(session, CommandResult):
            return session
        session.fill_chain.clear()
        return CommandResult.ok(status="Boundary cleared", changed=True)

    def fill_apply(self) -> CommandResult:
        session = self._session_for("fill")
        if isinstance(session, CommandResult):
            return session
        if len(session.fill_chain) < 2:
            return CommandResult.failure("Pick the curves or edges around the gap first (two or more, in order).")
        boundaries: list[dict[str, Any]] = []
        sources: list[str] = []
        for side in session.fill_chain:
            if "curve" in side:
                curve = next(curve for curve in self.state.curve_collection.curves if curve.id == side["curve"])
                boundaries.append({"points": _curve_points(curve), "continuity": "contact"})
            else:
                entity = self.state.model.get(side["entity"])
                if entity is None:
                    return CommandResult.failure("A boundary surface was deleted; clear the boundary and pick again.")
                boundaries.append({"brep": entity.brep, "edge": side["edge"], "continuity": side["continuity"]})
                sources.append(entity.id)
        scan_points = self._scan_points_near(boundaries) if session.fill_on_scan else None
        reply = self.worker.call("fill", boundaries, scan_points=scan_points)
        if not reply.ok:
            return _kernel_failure("Fill failed", reply)
        entity = entity_from_result(
            self.state.model, reply.value, tool="fill", params={"chain": [dict(side) for side in session.fill_chain], "on_scan": session.fill_on_scan}, sources=tuple(sources)
        )
        session.fill_chain.clear()
        return self._add_entities([entity], name="Fill Surface")

    # -- Extend --------------------------------------------------------------------------------

    def extend(self, entity_ids: tuple[str, ...] | None = None, distance: float | None = None) -> CommandResult:
        ids = entity_ids if entity_ids is not None else tuple(self.state.model.selected_ids)
        targets = [entity for entity in (self.state.model.get(value) for value in ids) if entity is not None and not entity.is_body]
        if not targets:
            return CommandResult.failure("Select a surface to extend (in the tree or the scene).")
        length = float(distance if distance is not None else (self.session.extend_distance if self.session else 5.0))
        if length <= 0:
            return CommandResult.failure("The extension distance must be positive.")
        replacements: list[tuple[ModelEntity, ModelEntity]] = []
        for target in targets:
            reply = self.worker.call("extend", target.brep, length)
            if not reply.ok:
                return _kernel_failure(f"Extending {target.name} failed", reply)
            grown = entity_from_result(self.state.model, reply.value, tool="extend", params={"distance": length}, sources=(target.id,), name=target.name)
            grown.color = target.color
            grown.kind = target.kind  # still the same kind of surface, only larger
            replacements.append((target, grown))
        before = self.state.model.snapshot()
        for old, new in replacements:
            index = self.state.model.entities.index(old)
            self.state.model.entities[index] = new
        self.state.model.selected_ids = [new.id for _old, new in replacements]
        self.state.model.revision += 1
        return self._changed("Extend Surface", before, f"Extended {len(replacements)} surface(s) by {length:g} {self.state.units}")

    # -- Trim ----------------------------------------------------------------------------------

    def trim_compute(self) -> CommandResult:
        session = self._session_for("trim")
        if isinstance(session, CommandResult):
            return session
        sources = [entity for entity in (self.state.model.get(value) for value in session.trim_sources) if entity is not None]
        if len(sources) < 2:
            return CommandResult.failure("Trimming needs two or more visible surfaces.")
        vertices, normals = self._world_scan_points(MAX_KERNEL_SCAN_POINTS)
        reply = self.worker.call(
            "trim",
            [entity.brep for entity in sources],
            vertices,
            normals,
            tolerance=session.trim_tolerance,
            overlap=session.trim_overlap,
        )
        if not reply.ok:
            return _kernel_failure("Trim failed", reply)
        pieces = reply.value["pieces"]
        for piece in pieces:
            piece["source_id"] = sources[int(piece["source"])].id
        session.trim_pieces = pieces
        kept = sum(1 for piece in pieces if piece["keep"])
        return CommandResult.ok(
            status=f"{len(pieces)} pieces, {kept} kept (on the scan). Click a piece to keep or drop it, then Apply.",
            changed=True,
        )

    def trim_toggle(self, index: int) -> CommandResult:
        session = self._session_for("trim")
        if isinstance(session, CommandResult):
            return session
        if session.trim_pieces is None or not 0 <= index < len(session.trim_pieces):
            return CommandResult.failure("Run the automatic trim first.")
        piece = session.trim_pieces[index]
        piece["keep"] = not piece["keep"]
        return CommandResult.ok(status=f"Piece {'kept' if piece['keep'] else 'dropped'}", changed=True)

    def trim_apply(self, *, sew: bool = True) -> CommandResult:
        session = self._session_for("trim")
        if isinstance(session, CommandResult):
            return session
        if session.trim_pieces is None:
            computed = self.trim_compute()
            if not computed.success:
                return computed
        assert session.trim_pieces is not None
        kept = [piece for piece in session.trim_pieces if piece["keep"]]
        if not kept:
            return CommandResult.failure("No piece is kept: click pieces to keep them.")
        sources = tuple(dict.fromkeys(piece["source_id"] for piece in kept))
        params = {"tolerance": session.trim_tolerance, "overlap": session.trim_overlap, "sources": list(session.trim_sources)}
        if sew:
            reply = self.worker.call("sew", [piece["brep"] for piece in kept], tolerance=session.sew_tolerance)
            if not reply.ok:
                return _kernel_failure("Sewing failed", reply)
            body = entity_from_result(self.state.model, reply.value, tool="trim", params={**params, "sew": True}, sources=sources)
            new_entities = [body]
            detail = body.stats
            if detail.get("solid"):
                status = f"Solid: volume {detail.get('volume', 0.0):,.1f} {self.state.units}^3"
            else:
                status = f"Shell with {detail.get('free_edges', 0)} open edges (not closed yet)"
        else:
            new_entities = []
            for piece in kept:
                source = self.state.model.get(piece["source_id"])
                entity = entity_from_result(self.state.model, {**piece, "kind": "piece"}, tool="trim", params=params, sources=(piece["source_id"],))
                if source is not None:
                    entity.color = source.color
                new_entities.append(entity)
            status = f"{len(new_entities)} trimmed surfaces"
        before = self.state.model.snapshot()
        for source_id in session.trim_sources:  # hidden, not deleted: trimming again stays possible
            self.state.model.set_visible(source_id, False)
        for entity in new_entities:
            self.state.model.add(entity)
        session.trim_pieces = None
        return self._changed("Trim Surfaces", before, status)

    # -- Compare -------------------------------------------------------------------------------

    def compare(self, entity_ids: tuple[str, ...] | None = None, *, tolerance: float | None = None) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("Open a scan first.")
        ids = entity_ids or tuple(entity.id for entity in self.state.model.visible())
        targets = [entity for entity in (self.state.model.get(value) for value in ids) if entity is not None]
        if not targets:
            return CommandResult.failure("There is nothing to compare yet: fit or build surfaces first.")
        display = self.state.mesh_object.display_mesh
        world = _apply(self.transform.current_object_matrix(), np.asarray(display.vertices, dtype=float))
        reply = self.worker.call("deviation", [entity.brep for entity in targets], world)
        if not reply.ok:
            return _kernel_failure("Compare failed", reply)
        band = float(tolerance if tolerance is not None else (self.session.fit.tolerance if self.session else 0.05))
        self.deviation = Deviation(np.asarray(reply.value, dtype=float), band, tuple(entity.id for entity in targets))
        stats = self.deviation.statistics()
        return CommandResult.ok(
            status=f"Deviation: RMS {stats['rms']:.3f}, max {stats['max']:.3f} {self.state.units}; "
            f"{100 * stats['within']:.1f}% within +/-{band:g}",
            changed=True,
        )

    def clear_deviation(self) -> CommandResult:
        self.deviation = None
        return CommandResult.ok(status="Deviation map cleared", changed=True)

    # -- entities ------------------------------------------------------------------------------

    def select_entities(self, entity_ids: tuple[str, ...]) -> CommandResult:
        valid = [value for value in entity_ids if self.state.model.get(value) is not None]
        self.state.model.selected_ids = valid
        return CommandResult.ok(status=f"{len(valid)} model item(s) selected" if valid else "Selection cleared", changed=True)

    def delete(self, entity_ids: tuple[str, ...] | None = None) -> CommandResult:
        ids = entity_ids if entity_ids is not None else tuple(self.state.model.selected_ids)
        if not ids:
            return CommandResult.failure("Select model items to delete.")
        before = self.state.model.snapshot()
        removed = self.state.model.remove(ids)
        if not removed:
            return CommandResult.failure("Nothing to delete.")
        return self._changed("Delete Model Items", before, f"Deleted {len(removed)} model item(s)")

    def set_visible(self, entity_id: str, visible: bool) -> CommandResult:
        before = self.state.model.snapshot()
        if not self.state.model.set_visible(entity_id, visible):
            return CommandResult.ok()
        return self._changed("Show" if visible else "Hide", before, "Shown" if visible else "Hidden")

    def rename(self, entity_id: str, name: str) -> CommandResult:
        entity = self.state.model.get(entity_id)
        if entity is None or not name.strip():
            return CommandResult.failure("Rename needs a model item and a name.")
        before = self.state.model.snapshot()
        entity.name = name.strip()
        self.state.model.revision += 1
        return self._changed("Rename", before, f"Renamed to {entity.name}")

    def export(self, path: str, *, file_format: str = "step", entity_ids: tuple[str, ...] | None = None) -> CommandResult:
        ids = entity_ids or tuple(self.state.model.selected_ids) or tuple(entity.id for entity in self.state.model.visible())
        targets = [entity for entity in (self.state.model.get(value) for value in ids) if entity is not None]
        if not targets:
            return CommandResult.failure("There is nothing to export yet.")
        reply = self.worker.call("export", [entity.brep for entity in targets], str(path), file_format=file_format)
        if not reply.ok:
            return _kernel_failure("Export failed", reply)
        info = reply.value
        warnings: tuple[str, ...] = ()
        if info["faces_back"] != info["faces"]:
            warnings = (f"The file reads back with {info['faces_back']} faces instead of {info['faces']}.",)
        return CommandResult.ok(status=f"Exported {len(targets)} item(s), {info['faces']} faces, to {path}", warnings=warnings)

    def shutdown(self) -> None:
        self.worker.shutdown()

    # -- helpers -------------------------------------------------------------------------------

    def _session_for(self, tool: str) -> ToolSession | CommandResult:
        if self.session is None or self.session.tool != tool:
            started = self.start(tool)
            if not started.success:
                return started
        assert self.session is not None
        return self.session

    def _add_entities(self, entities: list[ModelEntity], *, name: str) -> CommandResult:
        before = self.state.model.snapshot()
        for entity in entities:
            self.state.model.add(entity)
        self.state.model.selected_ids = [entity.id for entity in entities]
        first = entities[0]
        stats = first.stats
        detail = ""
        if "rms" in stats:
            detail = f": deviation RMS {stats['rms']:.3f}, max {stats.get('max_error', 0.0):.3f} {self.state.units}"
        return self._changed(name, before, f"Created {first.name}{detail}")

    def _changed(self, name: str, before: Any, status: str) -> CommandResult:
        after = self.state.model.snapshot()
        payload = CallbackUndoPayload(
            name,
            undo_action=lambda: self.state.model.restore(before),
            redo_action=lambda: self.state.model.restore(after),
        )
        return CommandResult.ok(status=status, changed=True, dirty=True, undo_payload=payload)

    def _default_brush_radius(self) -> float:
        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return 1.0
        vertices = np.asarray(mesh_object.display_mesh.vertices, dtype=float)
        if len(vertices) == 0:
            return 1.0
        return float(np.linalg.norm(vertices.max(axis=0) - vertices.min(axis=0)) * 0.03)

    def _source_mapping(self) -> SourceMapping:
        mesh_object = self.state.mesh_object
        assert mesh_object is not None
        display = mesh_object.display_mesh
        source = self.transform.transformed_source_mesh()
        key = (display.triangles, mesh_object.source_mesh)
        cached = self._mapping
        if cached is not None and cached[0][0] is key[0] and cached[0][1] is key[1]:
            return cached[1]
        selection = self.selection()
        assert selection is not None
        centroids = _apply(self.transform.current_object_matrix(), selection.centroids())
        mapping = SourceMapping(centroids, np.asarray(source.vertices), np.asarray(source.triangles))
        self._mapping = (key, mapping)
        return mapping

    def _selected_scan_data(self, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray | None]:
        """World-space points, local triangles and normals of the full-resolution selection."""

        mapping = self._source_mapping()
        chosen = mapping.source_triangles_for(mask)
        source = self.transform.transformed_source_mesh()
        points, triangles, used = selected_patch(np.asarray(source.vertices), np.asarray(source.triangles), chosen)
        normals = getattr(source, "vertex_normals", None)
        if normals is not None and len(normals) == len(source.vertices):
            return points, triangles, np.asarray(normals)[used]
        return points, triangles, None

    def _world_scan_points(self, limit: int) -> tuple[np.ndarray, np.ndarray]:
        source = self.transform.transformed_source_mesh()
        vertices = np.asarray(source.vertices, dtype=float)
        normals = getattr(source, "vertex_normals", None)
        if normals is None or len(normals) != len(vertices):
            from openretop.modeling.scan_selection import vertex_normals

            normals = vertex_normals(vertices, np.asarray(source.triangles, dtype=np.int64))
        normals = np.asarray(normals, dtype=float)
        if len(vertices) > limit:
            pick = np.random.default_rng(0).choice(len(vertices), limit, replace=False)
            vertices, normals = vertices[pick], normals[pick]
        return vertices, normals

    def _scan_points_near(self, boundaries: list[dict[str, Any]]) -> np.ndarray | None:
        """Scan points inside the fill's boundary region (by its bounding box), for "on scan"."""

        corners = [np.asarray(side["points"]) for side in boundaries if side.get("points") is not None]
        for side in boundaries:
            if side.get("brep") is not None:
                entity = next((item for item in self.state.model.entities if item.brep is side["brep"]), None)
                if entity is not None and side["edge"] < len(entity.edges):
                    corners.append(entity.edges[side["edge"]])
        if not corners or self.state.mesh_object is None:
            return None
        outline = np.vstack(corners)
        lower, upper = outline.min(axis=0), outline.max(axis=0)
        margin = 0.02 * float(np.linalg.norm(upper - lower))
        vertices, _normals = self._world_scan_points(MAX_KERNEL_SCAN_POINTS)
        inside = np.all((vertices >= lower - margin) & (vertices <= upper + margin), axis=1)
        points = vertices[inside]
        return points if len(points) >= 10 else None


def _apply(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    return points @ matrix[:3, :3].T + matrix[:3, 3]


def _curve_points(curve: Any) -> np.ndarray:
    for name in ("fitted_points", "points", "raw_points"):
        values = getattr(curve, name, None)
        if values is not None and len(values) >= 2:
            return np.asarray(values, dtype=float).reshape(-1, 3)
    raise ValueError(f"curve {getattr(curve, 'name', '?')} has no points")


def _kernel_failure(prefix: str, reply: KernelReply) -> CommandResult:
    message = f"{prefix}: {reply.error}"
    return CommandResult.failure(message, status=message)


__all__ = ("FitOptions", "ModelingController", "SELECTION_MODES", "TOOLS", "TOOL_TITLES", "ToolSession")
