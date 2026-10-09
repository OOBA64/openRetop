"""The surfacing tools (milestone S): Fit Surface, Loft, Fill, Extend, Trim, Compare, Export,
the 3D Sketch and the Section Sketch.

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
from openretop.modeling.profile2d import Profile2D, auto_tolerance, fit_profile
from openretop.modeling.sketch import MeshProjector, boundary_loop, curve_on_mesh, loop_polylines, region_inside

TOOLS = ("sketch", "section", "fit_surface", "loft", "fill", "extend", "trim", "compare")
SECTION_PLANES = {  # name: (in-plane u, in-plane v, the world axis the offset runs along)
    "XY": ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
    "YZ": ((0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (1.0, 0.0, 0.0)),
    "XZ": ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, 1.0, 0.0)),
}
TOOL_TITLES = {
    "fit_surface": "Fit Surface",
    "loft": "Loft",
    "fill": "Fill Surface",
    "extend": "Extend Surface",
    "trim": "Trim Surfaces",
    "compare": "Compare",
    "sketch": "3D Sketch",
    "section": "Section Sketch",
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
    # 3D Sketch: the curve being drawn (existing point id or None for a new point, position),
    # the pointer's spot on the scan and the live line through them
    sketch_points: list[tuple[str | None, np.ndarray]] = field(default_factory=list)
    hover: np.ndarray | None = None
    hover_node: str | None = None
    sketch_line: np.ndarray | None = None
    drag_node: str | None = None
    drag_before: Any = None
    face_fit_to_scan: bool = True
    # Section Sketch: the plane (a world plane and its offset), fit options, and what was
    # cut and fitted for the plane as it was (``section_key``)
    section_plane: str = "XY"
    section_offset: float = 0.0
    section_tolerance: float = 0.0  # 0 = automatic: from the noise measured on the section
    section_sharp: float = 0.0  # sharp-corner radius; 0 = automatic (5x the section's spacing)
    section_key: tuple[Any, ...] | None = None
    section_loops: list[np.ndarray] = field(default_factory=list)  # world polylines
    section_closed: list[bool] = field(default_factory=list)
    section_profiles: list[Profile2D] | None = None


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
        self._projector: tuple[tuple[object, object], MeshProjector] | None = None
        self._placed_line: tuple[bytes, np.ndarray] | None = None  # 3D Sketch preview cache
        self._normals_cache: tuple[object, np.ndarray] | None = None

    def discard_stale(self) -> None:
        """After undo/redo: drop tool state that may refer to surfaces that are gone."""

        session = self.session
        model = self.state.model
        model.selected_ids = [value for value in model.selected_ids if model.get(value) is not None]
        if session is not None:
            session.preview = None
            session.trim_pieces = None
            session.sketch_points = [(node, position) for node, position in session.sketch_points if node is None or node in model.sketch.nodes]
            session.sketch_line = None
            session.drag_node = None
            session.drag_before = None
            session.section_profiles = None
            if session.tool == "trim":
                session.trim_sources = tuple(entity.id for entity in model.visible() if not entity.is_body)
            session.fill_chain = [side for side in session.fill_chain if "curve" in side or model.get(side["entity"]) is not None]
        if self.deviation is not None and any(model.get(value) is None for value in self.deviation.entity_ids):
            self.deviation = None

    def reset(self) -> None:
        """A new project: no tool, no selection, no deviation map."""

        self.session = None
        self.deviation = None
        self._selection = None
        self._mapping = None
        self._projector = None
        self._normals_cache = None

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
        if tool in ("sketch", "fit_surface", "trim", "compare") and self.state.mesh_object is None:
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
        if tool == "section":
            if previous is not None and previous.tool == "section":
                self.session.section_plane, self.session.section_offset = previous.section_plane, previous.section_offset
            else:
                self.session.section_offset = self._scan_center(self.session.section_plane)
            self.section_cut()  # the section shows as soon as the tool opens
        hints = {
            "fit_surface": "Click the scan to select a smooth area (or brush it), then Fit.",
            "loft": "Select two or more curves, then Loft.",
            "fill": "Click curves or surface edges around the gap, in order; then Fill.",
            "extend": "Select a surface, set the distance, then Extend.",
            "trim": "Trim splits the surfaces by each other and keeps what lies on the scan.",
            "compare": "Compare colours the scan by its distance to the model.",
            "sketch": "Click points on the scan; Enter finishes a curve, clicking its first point closes it.",
            "section": "Pick a plane (click the scan to move it there), then Fit Profile and Create.",
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
            elif hasattr(session, key) and key not in (
                "tool", "fit", "preview", "trim_pieces", "fill_chain", "section_key", "section_loops", "section_closed", "section_profiles"
            ):
                current = getattr(session, key)
                setattr(session, key, type(current)(value) if current is not None else value)
            else:
                return CommandResult.failure(f"Unknown option: {key}")
        if values.get("selection_mode") is not None and session.selection_mode not in SELECTION_MODES:
            session.selection_mode = "smart"
        if session.section_plane not in SECTION_PLANES:
            session.section_plane = "XY"
        if any(key in values for key in ("section_tolerance", "section_sharp")):
            session.section_profiles = None  # fitted for other options
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
        if selection is None:
            return outcome
        mask = selection.mask.copy()
        selection.clear()
        payload = outcome.undo_payload
        if payload is None:
            return outcome

        def undo() -> None:  # the surface goes, and the area it was fitted to comes back
            payload.undo()
            current = self.selection()
            if current is not None and len(current.mask) == len(mask):
                current.set_mask(mask)

        def redo() -> None:
            payload.redo()
            current = self.selection()
            if current is not None:
                current.clear()

        return CommandResult.ok(
            status=outcome.status,
            changed=True,
            dirty=True,
            undo_payload=CallbackUndoPayload(payload.name, undo_action=undo, redo_action=redo),
        )

    # -- Section Sketch ------------------------------------------------------------------------

    def section_frame(self) -> dict[str, list[float]] | None:
        """The sketch plane as origin + in-plane axes (world), for the session's plane."""

        session = self.session
        if session is None or session.section_plane not in SECTION_PLANES:
            return None
        u, v, axis = (np.asarray(value) for value in SECTION_PLANES[session.section_plane])
        return {"origin": (axis * session.section_offset).tolist(), "u": u.tolist(), "v": v.tolist()}

    def section_set_plane(self, plane: str, *, offset: float | None = None) -> CommandResult:
        session = self._session_for("section")
        if isinstance(session, CommandResult):
            return session
        if plane not in SECTION_PLANES:
            return CommandResult.failure(f"Unknown sketch plane: {plane} (use {', '.join(SECTION_PLANES)}).")
        changed_plane = plane != session.section_plane
        session.section_plane = plane
        if offset is not None:
            session.section_offset = float(offset)
        elif changed_plane:
            session.section_offset = self._scan_center(plane)
        return self.section_cut()

    def section_place(self, world_point: object) -> CommandResult:
        """Move the plane (keeping its direction) through a point picked on the scan."""

        session = self._session_for("section")
        if isinstance(session, CommandResult):
            return session
        axis = np.asarray(SECTION_PLANES[session.section_plane][2])
        session.section_offset = float(np.asarray(world_point, dtype=float) @ axis)
        return self.section_cut()

    def section_cut(self) -> CommandResult:
        """The scan's section on the plane (cached for the plane as it is)."""

        session = self._session_for("section")
        if isinstance(session, CommandResult):
            return session
        if self.state.mesh_object is None:
            return CommandResult.failure("Open a scan first (File > Open Model).")
        from openretop.geometry.sections import extract_section_by_plane

        source = self.transform.transformed_source_mesh()
        key = (session.section_plane, round(session.section_offset, 9), id(source.vertices), len(source.vertices))
        if session.section_key != key:
            axis = np.asarray(SECTION_PLANES[session.section_plane][2])
            section = extract_section_by_plane(source, axis * session.section_offset, axis)
            usable = [poly for poly in section.polylines if poly.point_count >= 8]
            session.section_loops = [np.asarray(poly.points, dtype=float) for poly in usable]
            session.section_closed = [bool(poly.is_closed) for poly in usable]
            session.section_key = key
            session.section_profiles = None
        count = len(session.section_loops)
        where = f"{session.section_plane} at {session.section_offset:.3f} {self.state.units}"
        if count == 0:
            return CommandResult.ok(status=f"Section Sketch: the plane ({where}) misses the scan.", changed=True)
        return CommandResult.ok(status=f"Section Sketch: {count} section loop(s) on {where}. Fit Profile fits lines and arcs.", changed=True)

    def section_fit(self) -> CommandResult:
        """Lines and arcs within the tolerance through each loop of the section."""

        cut = self.section_cut()
        if not cut.success:
            return cut
        session = self.session
        assert session is not None
        if not session.section_loops:
            return CommandResult.failure("The plane misses the scan: move it (click the scan, or set the offset).")
        tolerance = self.section_tolerance_in_use()
        sharp = session.section_sharp if session.section_sharp > 0 else None
        profiles = [fit_profile(outline, tolerance=tolerance, sharp_radius=sharp) for outline in self._section_outlines()]
        session.section_profiles = profiles
        lines = sum(1 for profile in profiles for segment in profile.segments if segment.kind == "line")
        arcs = sum(1 for profile in profiles for segment in profile.segments if segment.kind == "arc")
        worst = max(profile.deviation for profile in profiles)
        rms = float(np.sqrt(np.mean([profile.rms**2 for profile in profiles])))
        auto = " (auto)" if session.section_tolerance <= 0 else ""
        return CommandResult.ok(
            status=f"Profile: {lines} lines, {arcs} arcs in {len(profiles)} loop(s) at tolerance {tolerance:.3f}{auto}; "
            f"deviation RMS {rms:.3f}, max {worst:.3f} {self.state.units}. Create keeps it.",
            changed=True,
        )

    def section_tolerance_in_use(self) -> float:
        """The tolerance set, or (0 = Auto) one from the noise measured on the section."""

        session = self.session
        if session is None:
            return 0.05
        if session.section_tolerance > 0:
            return float(session.section_tolerance)
        return auto_tolerance(self._section_outlines())

    def _section_outlines(self) -> list[np.ndarray]:
        """The section loops in the plane's 2D coordinates."""

        session = self.session
        frame = self.section_frame()
        if session is None or frame is None:
            return []
        u, v, origin = (np.asarray(frame[name]) for name in ("u", "v", "origin"))
        return [np.c_[(loop - origin) @ u, (loop - origin) @ v] for loop in session.section_loops]

    def section_profile_lines(self) -> list[np.ndarray]:
        """The fitted profile in world coordinates (for display)."""

        session = self.session
        frame = self.section_frame()
        if session is None or session.section_profiles is None or frame is None:
            return []
        from openretop.cad_kernel.profiles import PlaneFrame

        plane = PlaneFrame.from_dict(frame)
        return [plane.to_world(profile.polyline(16)) for profile in session.section_profiles if profile.segments]

    def section_plane_outline(self) -> np.ndarray | None:
        """A rectangle a little larger than the scan on the plane (for display)."""

        frame = self.section_frame()
        if frame is None or self.state.mesh_object is None:
            return None
        source = self.transform.transformed_source_mesh()
        vertices = np.asarray(source.vertices, dtype=float)
        if len(vertices) == 0:
            return None
        from openretop.cad_kernel.profiles import PlaneFrame

        plane = PlaneFrame.from_dict(frame)
        local = plane.to_plane(vertices[:: max(1, len(vertices) // 20000)])
        low, high = local.min(axis=0), local.max(axis=0)
        margin = 0.08 * float(np.linalg.norm(high - low))
        low, high = low - margin, high + margin
        corners = np.array([[low[0], low[1]], [high[0], low[1]], [high[0], high[1]], [low[0], high[1]], [low[0], low[1]]])
        return plane.to_world(corners)

    def section_create(self) -> CommandResult:
        """Keep the fitted profile as a sketch: exact lines and arcs, closed loops as faces."""

        session = self._session_for("section")
        if isinstance(session, CommandResult):
            return session
        if session.section_profiles is None:
            fitted = self.section_fit()
            if not fitted.success:
                return fitted
        profiles = [profile for profile in session.section_profiles or [] if profile.segments]
        if not profiles:
            return CommandResult.failure("Nothing to create: fit a profile first.")
        frame = self.section_frame()
        assert frame is not None
        loops = [profile.to_dict() for profile in profiles]
        worst = max(profile.deviation for profile in profiles)
        rms = float(np.sqrt(np.mean([profile.rms**2 for profile in profiles])))
        reply = self.worker.call("profile", frame, loops, rms=rms, max_error=worst)
        if not reply.ok:
            return _kernel_failure("Sketch failed", reply)
        params = {
            "plane": session.section_plane,
            "offset": session.section_offset,
            "frame": frame,
            "loops": loops,
            "tolerance": self.section_tolerance_in_use(),
        }
        entity = entity_from_result(self.state.model, reply.value, tool="section", params=params)
        session.section_profiles = None  # created: the next Fit starts afresh
        return self._add_entities([entity], name="Section Sketch")

    def _scan_center(self, plane: str) -> float:
        if self.state.mesh_object is None or plane not in SECTION_PLANES:
            return 0.0
        vertices = np.asarray(self.transform.transformed_source_mesh().vertices, dtype=float)
        if len(vertices) == 0:
            return 0.0
        axis = np.asarray(SECTION_PLANES[plane][2])
        values = vertices @ axis
        return float(0.5 * (values.min() + values.max()))

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

    def set_visibility(self, entity_ids: tuple[str, ...], visible: bool | None, *, isolate: bool = False) -> CommandResult:
        """Show, hide or toggle (``visible`` None) the given items in one undo step.

        ``isolate`` shows them and hides every other model item (Shift+H).
        """

        model = self.state.model
        targets = [entity for entity in (model.get(value) for value in entity_ids) if entity is not None]
        if not targets:
            return CommandResult.failure("Select model items first.")
        before = model.snapshot()
        wanted = {entity.id for entity in targets}
        changed = 0
        for entity in model.entities:
            if entity.id in wanted:
                value = (not entity.visible) if visible is None else (True if isolate else visible)
            elif isolate:
                value = False
            else:
                continue
            changed += int(model.set_visible(entity.id, value))
        if not changed:
            return CommandResult.ok(status="Nothing to change")
        name = "Isolate" if isolate else ("Toggle Visibility" if visible is None else ("Show" if visible else "Hide"))
        return self._changed(name, before, f"{name}: {len(targets)} model item(s)")

    def show_all(self) -> CommandResult:
        hidden = tuple(entity.id for entity in self.state.model.entities if not entity.visible)
        if not hidden:
            return CommandResult.ok(status="Everything in the model is shown")
        return self.set_visibility(hidden, True)

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

    # -- 3D Sketch -------------------------------------------------------------------------------

    def sketch_projector(self) -> MeshProjector | None:
        """The full-resolution scan in world coordinates, for laying curves on it."""

        mesh_object = self.state.mesh_object
        if mesh_object is None:
            return None
        source = self.transform.transformed_source_mesh()
        key = (source.vertices, source.triangles)
        cached = self._projector
        if cached is not None and cached[0][0] is key[0] and cached[0][1] is key[1]:
            return cached[1]
        projector = MeshProjector(np.asarray(source.vertices), np.asarray(source.triangles))
        self._projector = (key, projector)
        return projector

    def sketch_click(self, world_point: object | None, node_id: str | None = None) -> CommandResult:
        """Place the next point (or snap to an existing one: that connects and finishes)."""

        session = self._session_for("sketch")
        if isinstance(session, CommandResult):
            return session
        sketch = self.state.model.sketch
        drawing = session.sketch_points
        if node_id is not None and node_id in sketch.nodes:
            position = sketch.nodes[node_id]
            if len(drawing) >= 3 and drawing[0][0] == node_id:
                return self.sketch_finish(close=True)  # back to the first point: a closed curve
            if drawing and drawing[0][0] == node_id:
                return CommandResult.ok(status="A closed curve needs at least three points.")
            drawing.append((node_id, position.copy()))
            if len(drawing) >= 2:
                return self.sketch_finish()  # joined another curve at its point: connected, done
            session.sketch_line = self._sketch_preview_line(session)
            return CommandResult.ok(status="Curve started at an existing point.", changed=True)
        if world_point is None:
            return CommandResult.ok(status="Click on the scan to place a point.")
        projector = self.sketch_projector()
        if projector is None:
            return CommandResult.failure("Open a scan first.")
        snapped, _triangle = projector.project(np.asarray(world_point, dtype=float).reshape(1, 3))
        if drawing and np.linalg.norm(snapped[0] - drawing[-1][1]) < 0.25 * projector.spacing:
            return CommandResult.ok(status="That point is already placed.")
        drawing.append((None, snapped[0]))
        session.sketch_line = self._sketch_preview_line(session)
        return CommandResult.ok(
            status=f"{len(drawing)} point(s). Enter finishes; click the first point to close; Backspace removes the last.",
            changed=True,
        )

    def sketch_hover(self, world_point: object | None, node_id: str | None = None) -> None:
        session = self.session
        if session is None or session.tool != "sketch":
            return
        session.hover_node = node_id
        if node_id is not None:
            session.hover = self.state.model.sketch.nodes.get(node_id)
        elif world_point is None:
            session.hover = None
        else:
            session.hover = np.asarray(world_point, dtype=float).reshape(3)
        session.sketch_line = self._sketch_preview_line(session)

    def _sketch_preview_line(self, session: ToolSession) -> np.ndarray | None:
        """The live curve: the placed points' curve (kept between mouse moves) plus a span
        from the last point to the pointer, so a move costs one span, not the whole curve."""

        projector = self.sketch_projector()
        placed = np.asarray([position for _node, position in session.sketch_points], dtype=float).reshape(-1, 3)
        if projector is None or not len(placed):
            return None
        key = placed.tobytes()
        if self._placed_line is None or self._placed_line[0] != key:
            line = curve_on_mesh(placed, projector, smoothing=0) if len(placed) >= 2 else placed.copy()
            self._placed_line = (key, line)
        line = self._placed_line[1]
        if session.hover is None:
            return line if len(line) >= 2 else None
        span = curve_on_mesh(np.vstack([placed[-1], session.hover]), projector, smoothing=0)
        return np.vstack([line, span[1:]])

    def sketch_finish(self, *, close: bool = False) -> CommandResult:
        session = self._session_for("sketch")
        if isinstance(session, CommandResult):
            return session
        drawing = session.sketch_points
        needed = 3 if close else 2
        if len(drawing) < needed:
            kind = "closed curve" if close else "curve"
            return CommandResult.failure(f"A {kind} needs at least {needed} points.")
        projector = self.sketch_projector()
        if projector is None:
            return CommandResult.failure("Open a scan first.")
        before = self.state.model.snapshot()
        sketch = self.state.model.sketch
        nodes = [node if node is not None else sketch.new_node(position) for node, position in drawing]
        if close and nodes[-1] == nodes[0]:
            nodes = nodes[:-1]
        curve = sketch.add_curve(nodes, projector, closed=close)
        session.sketch_points = []
        session.sketch_line = None
        self.state.model.selected_curve_ids = [curve.id]
        self.state.model.revision += 1
        kind = "closed curve" if close else "curve"
        return self._changed("Sketch Curve", before, f"{curve.name}: {kind} through {len(nodes)} points")

    def sketch_undo_point(self) -> CommandResult:
        session = self.session
        if session is None or session.tool != "sketch" or not session.sketch_points:
            return CommandResult.ok(status="No point to remove.")
        session.sketch_points.pop()
        session.sketch_line = self._sketch_preview_line(session)
        return CommandResult.ok(status=f"{len(session.sketch_points)} point(s)", changed=True)

    def sketch_cancel(self) -> bool:
        """Drop the curve being drawn; False when there was none."""

        session = self.session
        if session is None or session.tool != "sketch" or not session.sketch_points:
            return False
        session.sketch_points = []
        session.sketch_line = None
        return True

    def sketch_move_node(self, node_id: str, world_point: object, *, final: bool = False) -> CommandResult:
        """Drag a point along the scan; every curve through it follows (one undo step)."""

        session = self._session_for("sketch")
        if isinstance(session, CommandResult):
            return session
        sketch = self.state.model.sketch
        projector = self.sketch_projector()
        if projector is None or node_id not in sketch.nodes:
            return CommandResult.failure("No such point.")
        if session.drag_before is None:
            session.drag_before = self.state.model.snapshot()
        sketch.move_node(node_id, world_point, projector)
        self.state.model.revision += 1
        if not final:
            return CommandResult.ok(changed=True)
        before, session.drag_before = session.drag_before, None
        return self._changed("Move Sketch Point", before, "Point moved")

    def sketch_select_curves(self, curve_ids: tuple[str, ...], *, add: bool = False) -> CommandResult:
        sketch = self.state.model.sketch
        valid = [value for value in curve_ids if sketch.curve(value) is not None]
        if add:
            current = list(self.state.model.selected_curve_ids)
            for value in valid:
                if value in current:
                    current.remove(value)
                else:
                    current.append(value)
            valid = current
        self.state.model.selected_curve_ids = valid
        self.state.model.revision += 1
        return CommandResult.ok(status=f"{len(valid)} sketch curve(s) selected" if valid else "No sketch curve selected", changed=True)

    def sketch_delete(self, curve_ids: tuple[str, ...] | None = None) -> CommandResult:
        ids = curve_ids if curve_ids is not None else tuple(self.state.model.selected_curve_ids)
        if not ids:
            return CommandResult.failure("Select sketch curves to delete.")
        before = self.state.model.snapshot()
        removed = self.state.model.sketch.remove_curves(ids)
        if not removed:
            return CommandResult.failure("Nothing to delete.")
        gone = set(ids)
        self.state.model.selected_curve_ids = [value for value in self.state.model.selected_curve_ids if value not in gone]
        self.state.model.revision += 1
        return self._changed("Delete Sketch Curves", before, f"Deleted {removed} sketch curve(s)")

    def sketch_loft(self, curve_ids: tuple[str, ...] | None = None) -> CommandResult:
        ids = curve_ids if curve_ids is not None else tuple(self.state.model.selected_curve_ids)
        curves = [curve for curve in (self.state.model.sketch.curve(value) for value in ids) if curve is not None]
        if len(curves) < 2:
            return CommandResult.failure("Select two or more sketch curves to loft between (Ctrl+click them).")
        if any(curve.closed for curve in curves) and not all(curve.closed for curve in curves):
            return CommandResult.failure("Loft between curves that are all open or all closed.")
        reply = self.worker.call("loft", [curve.polyline for curve in curves])
        if not reply.ok:
            return _kernel_failure("Loft failed", reply)
        entity = entity_from_result(self.state.model, reply.value, tool="loft", params={"sketch_curves": [curve.id for curve in curves]})
        return self._add_entities([entity], name="Loft")

    def sketch_face(self, curve_ids: tuple[str, ...] | None = None, *, fit_to_scan: bool | None = None) -> CommandResult:
        """A face inside a closed curve or a loop of curves, fitted to the scan inside it."""

        ids = list(curve_ids if curve_ids is not None else self.state.model.selected_curve_ids)
        sketch = self.state.model.sketch
        chain = boundary_loop(sketch, ids)
        if chain is None:
            return CommandResult.failure(
                "Select one closed curve, or curves whose ends meet in a loop (draw them by snapping to existing end points)."
            )
        boundaries = loop_polylines(chain)
        session = self.session
        on_scan = fit_to_scan if fit_to_scan is not None else (session.face_fit_to_scan if session is not None else True)
        projector = self.sketch_projector()
        reply = None
        if on_scan and projector is not None:
            inside = region_inside(projector, np.vstack(boundaries), grow=3)
            if int(np.count_nonzero(inside)) >= 30:
                points, triangles, _used = selected_patch(projector.vertices, projector.triangles, np.nonzero(inside)[0])
                options = session.fit if session is not None else FitOptions()
                reply = self.worker.call(
                    "patch_from_curves", points, triangles, boundaries, tolerance=options.tolerance, smoothness=options.smoothness
                )
                if not reply.ok:
                    return _kernel_failure("Face failed", reply)
        if reply is None:
            reply = self.worker.call("fill", [{"points": line, "continuity": "contact"} for line in boundaries])
            if not reply.ok:
                return _kernel_failure("Face failed", reply)
        entity = entity_from_result(
            self.state.model,
            reply.value,
            tool="sketch_face",
            params={"sketch_curves": [curve.id for curve, _reverse in chain], "fit_to_scan": on_scan},
        )
        return self._add_entities([entity], name="Face From Curves")

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
        return points, triangles, self._scan_normals()[used]

    def _scan_normals(self) -> np.ndarray:
        """Vertex normals of the (world-space) scan: the file's, or computed once.

        A cylinder or cone fit starts from them; without normals its first guess on a
        partial arc can miss badly (an R12 boss came out as freeform at 0.67 mm RMS).
        """

        source = self.transform.transformed_source_mesh()
        normals = getattr(source, "vertex_normals", None)
        if normals is not None and len(normals) == len(source.vertices):
            return np.asarray(normals, dtype=float)
        cached = self._normals_cache
        if cached is not None and cached[0] is source.vertices:
            return cached[1]
        from openretop.modeling.scan_selection import vertex_normals

        computed = vertex_normals(np.asarray(source.vertices, dtype=float), np.asarray(source.triangles, dtype=np.int64))
        self._normals_cache = (source.vertices, computed)
        return computed

    def _world_scan_points(self, limit: int) -> tuple[np.ndarray, np.ndarray]:
        source = self.transform.transformed_source_mesh()
        vertices = np.asarray(source.vertices, dtype=float)
        normals = self._scan_normals()
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


__all__ = ("FitOptions", "ModelingController", "SECTION_PLANES", "SELECTION_MODES", "TOOLS", "TOOL_TITLES", "ToolSession")
