"""The surfacing tools (milestone S): Fit Surface, Loft, Fill, Extend, Trim, Compare, Export,
the Surface Sketch and the Section Sketch.

Each tool is a session: ``start`` it, adjust it (selection, options, picks), ``apply`` it.
Geometry is made by the kernel worker (``cad_kernel.jobs``), so a kernel crash or hang comes
back as a failed ``CommandResult``. New entities go into ``state.model`` with an undo entry.

Coordinates: the selection lives on the display mesh in its own (object) coordinates, like
the scan actor; everything sent to the kernel is in world coordinates, so the surfaces line
up with the scan as shown and export where they appear.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from openretop.application.controller_support import CallbackUndoPayload, ControllerBase
from openretop.application.events import EventPublisher
from openretop.application.regeneration import regenerate, replace_entity
from openretop.application.results import CommandResult
from openretop.application.sketch_mode import PLANES as SKETCH_PLANES
from openretop.application.sketch_mode import SketchMode
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

TOOLS = ("sketch", "plane_sketch", "section", "extrude", "fit_surface", "loft", "fill", "extend", "trim", "compare")
EXTRUDE_MODES = ("new", "add", "cut")
SECTION_PLANES = SKETCH_PLANES  # name: (in-plane u, in-plane v, the world axis the offset runs along)
TOOL_TITLES = {
    "fit_surface": "Fit Surface",
    "loft": "Loft",
    "fill": "Fill Surface",
    "extend": "Extend Surface",
    "trim": "Trim Surfaces",
    "compare": "Compare",
    "sketch": "Surface Sketch",
    "plane_sketch": "3D Sketch",
    "section": "Section Sketch",
    "extrude": "Extrude",
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
    trim_manual: bool = False  # keep every piece; the user drops the ones to go
    trim_selected: tuple[str, ...] = ()  # surfaces selected when the tool opened
    trim_used: tuple[str, ...] = ()  # the surfaces the pieces came from
    trim_drawing: bool = False  # clicks place the points of a cut line
    trim_cut: list[np.ndarray] = field(default_factory=list)  # the cut line being drawn (world)
    trim_cut_direction: np.ndarray | None = None  # the view direction it was drawn along
    trim_cuts: list[dict[str, Any]] = field(default_factory=list)  # finished cut lines
    # Surface Sketch: the curve being drawn (existing point id or None for a new point, position),
    # the pointer's spot on the scan and the live line through them
    sketch_points: list[tuple[str | None, np.ndarray]] = field(default_factory=list)
    hover: np.ndarray | None = None
    hover_node: str | None = None
    sketch_line: np.ndarray | None = None
    drag_node: str | None = None
    drag_before: Any = None
    face_fit_to_scan: bool = True
    sketch_smoothness: float = 0.6  # for new curves (and the one being drawn)
    sketch_feature: bool = False  # new curves follow the scan's creases (body lines)
    selected_node: str | None = None  # a sketch point picked for editing
    show_creases: bool = False  # colour the scan by its creases (body lines)
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
    section_selected: tuple[str, int, int] | None = None  # ("vertex" or "segment", loop, index)
    section_drag_before: Any = None
    section_editing: str = ""  # the sketch entity being edited: Create replaces it
    # Extrude: the sketch, the body to add to / cut from, depths along the sketch's normal
    # (front ahead of the plane, back behind it), draft in degrees; with ``extrude_auto`` the
    # depths come from the scan and each hole keeps its own (a pocket stays a pocket)
    extrude_profile: str = ""
    extrude_target: str = ""
    extrude_mode: str = "new"
    extrude_front: float = 10.0
    extrude_back: float = 0.0
    extrude_draft: float = 0.0
    extrude_auto: bool = True
    extrude_holes: dict[int, tuple[float, float]] = field(default_factory=dict)  # loop -> measured range
    extrude_regions: list[str] = field(default_factory=list)  # a 3D Sketch's picked regions (none: all)
    # 3D Sketch (Solid): the constrained sketch being drawn, and the scan's cut on its plane
    sketch2d: SketchMode | None = None
    sketch2d_reference: list[np.ndarray] = field(default_factory=list)
    sketch2d_reference_key: tuple[Any, ...] | None = None


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
        self._handles: tuple[tuple[str, int], dict[str, Any]] | None = None  # (entity, brep) -> its sides
        self._placed_line: tuple[bytes, np.ndarray] | None = None  # Surface Sketch preview cache
        self._normals_cache: tuple[object, np.ndarray] | None = None
        self._crease_cache: tuple[object, np.ndarray] | None = None

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
            if session.selected_node not in model.sketch.nodes:
                session.selected_node = None
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
        if tool in ("sketch", "fit_surface", "compare") and self.state.mesh_object is None:
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
            model = self.state.model
            self.session.trim_sources = tuple(entity.id for entity in model.visible() if not entity.is_body)
            picked = [entity for entity in (model.get(value) for value in model.selected_ids) if entity is not None and not entity.is_body]
            self.session.trim_selected = tuple(entity.id for entity in picked)
        if tool == "sketch":
            if previous is not None and previous.tool == "sketch":
                self.session.sketch_smoothness, self.session.sketch_feature = previous.sketch_smoothness, previous.sketch_feature
                self.session.show_creases = previous.show_creases
            projector = self.sketch_projector()
            if projector is not None:
                projector.graph  # noqa: B018  # built now (in the background), not on the first click
        if tool == "section":
            if previous is not None and previous.tool == "section":
                self.session.section_plane, self.session.section_offset = previous.section_plane, previous.section_offset
            else:
                self.session.section_offset = self._scan_center(self.session.section_plane)
            self.section_cut()  # the section shows as soon as the tool opens
        if tool == "plane_sketch":
            plane = previous.sketch2d.plane if previous is not None and previous.sketch2d is not None else "XY"
            self.session.sketch2d = SketchMode(plane=plane, offset=self._scan_center(plane))
            self._sketch2d_reference()
        if tool == "extrude":
            profile = self._extrude_profile_entity()
            if profile is None:
                self.session = previous
                return CommandResult.failure("Make a sketch first (3D Sketch or Section Sketch), then Extrude it.")
            self.session.extrude_profile = profile.id
            bodies = [entity for entity in self.state.model.entities if entity.kind == "solid"]
            selected = [entity for entity in bodies if entity.id in self.state.model.selected_ids]
            target = selected[0] if selected else (bodies[-1] if bodies else None)
            self.session.extrude_target = "" if target is None else target.id
            self.session.extrude_mode = "add" if target is not None else "new"
            self.extrude_measure()
            self.extrude_preview()  # shown at once; a failure here just means no preview yet
        hints = {
            "fit_surface": "Click the scan to select a smooth area (or brush it), then Fit.",
            "loft": "Select two or more curves, then Loft.",
            "fill": "Click curves or surface edges around the gap, in order; then Fill.",
            "extend": "Select a surface, set the distance, then Extend.",
            "trim": "Split the surfaces by each other, or draw a Cut Line across one; click the pieces to cut away, then Apply.",
            "compare": "Compare colours the scan by its distance to the model.",
            "sketch": "Click points on the scan; Enter finishes a curve, clicking its first point closes it. Click a point to edit it; double-click a curve to add a point.",
            "section": "Pick a plane (click the scan to move it there), then Fit Profile and Create.",
            "plane_sketch": "Draw lines, rectangles, circles and arcs on the plane; constrain and dimension them; Finish Sketch.",
            "extrude": "Extrude the sketch: the depth comes from the scan; adjust it, choose new / add / cut, then Create.",
        }
        return CommandResult.ok(status=f"{TOOL_TITLES[tool]}: {hints[tool]}", changed=True, metadata={"tool": tool})

    def finish(self) -> CommandResult:
        tool = self.tool
        session = self.session
        if session is not None and session.sketch2d is not None and session.sketch2d.sketch.curves:
            # closing a 3D Sketch keeps what was drawn (Fusion's Finish Sketch), never drops it
            return self.sketch2d_finish()
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
                "tool", "fit", "preview", "trim_pieces", "fill_chain", "section_key", "section_loops", "section_closed", "section_profiles",
                "extrude_holes", "selected_node", "section_selected", "section_drag_before", "section_editing",
                "trim_drawing", "trim_cut", "trim_cut_direction", "trim_cuts", "trim_selected", "trim_used",
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
        if session.extrude_mode not in EXTRUDE_MODES:
            session.extrude_mode = "new"
        if any(key.startswith("extrude_") for key in values):
            session.preview = None
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
            session.section_selected = None
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
        session.section_selected = None
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
            "rms": rms,
            "max_error": worst,
        }
        model = self.state.model
        replaced = model.get(session.section_editing) if session.section_editing else None
        session.section_profiles = None  # created: the next Fit starts afresh
        session.section_selected = None
        session.section_editing = ""
        if replaced is None:
            entity = entity_from_result(model, reply.value, tool="section", params=params)
            added = self._add_entities([entity], name="Section Sketch")
            if added.success:
                model.timeline.add("sketch", entity.id, params, result=reply.value)
            return added
        before = model.snapshot()
        replace_entity(model, replaced.id, reply.value, tool="section", params=params)  # same id, same place
        model.selected_ids = [replaced.id]
        feature = model.timeline.maker(replaced.id)
        if feature is None:  # a sketch from before the history: it starts one now
            model.timeline.add("sketch", replaced.id, params, result=reply.value)
            return self._changed("Edit Sketch", before, f"Updated {replaced.name}")
        feature.inputs = dict(params)
        feature.result = reply.value
        feature.status, feature.message = "ok", ""
        later = model.timeline.features[model.timeline.index(feature.id) + 1 :]
        if not any(feature.id in item.reads() for item in later):
            model.revision += 1
            return self._changed("Edit Sketch", before, f"Updated {replaced.name}")
        report = regenerate(model, self.worker, later[0].id)
        return self._changed("Edit Sketch", before, f"Updated {replaced.name}. {report.summary()}")

    # -- editing the profile by hand -------------------------------------------------------------

    def section_edit_entity(self, entity_id: str | None = None) -> CommandResult:
        """Open a sketch made earlier for editing (Create then replaces it)."""

        model = self.state.model
        ids = [entity_id] if entity_id else list(model.selected_ids)
        candidates = [model.get(value) for value in ids]
        entity = next((item for item in candidates if item is not None and item.kind == "profile"), None)
        if entity is None:
            return CommandResult.failure("Select a sketch (in the tree) to edit.")
        if "sketch2d" in entity.params:
            return self.sketch2d_edit(entity.id)
        started = self.start("section")
        if not started.success:
            return started
        session = self.session
        assert session is not None
        params = entity.params
        session.section_plane = str(params.get("plane", "XY"))
        session.section_offset = float(params.get("offset", 0.0))
        session.section_tolerance = float(params.get("tolerance", 0.0))
        self.section_cut()
        session.section_profiles = [Profile2D.from_dict(loop) for loop in params.get("loops", [])]
        session.section_editing = entity.id
        for index in range(len(session.section_profiles)):
            self._remeasure(index)
        return CommandResult.ok(status=f"Editing {entity.name}: drag its corners, pick a segment to change it; Create updates it.", changed=True)

    def _section_plane_point(self, world_point: object) -> np.ndarray:
        frame = self.section_frame()
        assert frame is not None
        u, v, origin = (np.asarray(frame[name]) for name in ("u", "v", "origin"))
        local = np.asarray(world_point, dtype=float).reshape(3) - origin
        return np.array([float(local @ u), float(local @ v)])

    def section_vertices_world(self) -> list[tuple[int, int, np.ndarray]]:
        """Every corner of the fitted profile: (loop, vertex, world position)."""

        from openretop.modeling import profile_edit

        session = self.session
        frame = self.section_frame()
        if session is None or session.section_profiles is None or frame is None:
            return []
        from openretop.cad_kernel.profiles import PlaneFrame

        plane = PlaneFrame.from_dict(frame)
        result = []
        for loop, profile in enumerate(session.section_profiles):
            if not profile.segments:
                continue
            for index, position in enumerate(plane.to_world(profile_edit.vertices(profile))):
                result.append((loop, index, position))
        return result

    def section_segments_world(self) -> list[tuple[int, int, np.ndarray]]:
        """Every segment of the fitted profile as a world polyline: (loop, segment, line)."""

        session = self.session
        frame = self.section_frame()
        if session is None or session.section_profiles is None or frame is None:
            return []
        from openretop.cad_kernel.profiles import PlaneFrame

        plane = PlaneFrame.from_dict(frame)
        return [
            (loop, index, plane.to_world(segment.sample(24)))
            for loop, profile in enumerate(session.section_profiles)
            for index, segment in enumerate(profile.segments)
        ]

    def section_select(self, kind: str | None, loop: int = 0, index: int = 0) -> CommandResult:
        session = self._session_for("section")
        if isinstance(session, CommandResult):
            return session
        if kind is None or session.section_profiles is None:
            session.section_selected = None
            return CommandResult.ok(status="Nothing selected", changed=True)
        session.section_selected = (kind, int(loop), int(index))
        from openretop.modeling import profile_edit

        if kind == "segment":
            segment = session.section_profiles[loop].segments[index]
            return CommandResult.ok(status=f"{profile_edit.describe(segment)}. Right-click for changes.", changed=True)
        return CommandResult.ok(status="Corner selected: drag it in the sketch plane; right-click to round or sharpen it.", changed=True)

    def section_move_vertex(self, loop: int, index: int, world_point: object, *, final: bool = False) -> CommandResult:
        """Drag a corner (``world_point`` on the sketch plane); one undo step per drag."""

        from openretop.modeling import profile_edit

        session = self._session_for("section")
        if isinstance(session, CommandResult):
            return session
        if session.section_profiles is None:
            return CommandResult.failure("Fit a profile first.")
        if session.section_drag_before is None:
            session.section_drag_before = copy.deepcopy(session.section_profiles)
        profile_edit.move_vertex(session.section_profiles[loop], index, self._section_plane_point(world_point))
        self._remeasure(loop)
        if not final:
            return CommandResult.ok(changed=True)
        before, session.section_drag_before = session.section_drag_before, None
        return self._profile_changed("Move Sketch Corner", before, "Corner moved")

    def section_edit(self, operation: str, value: float | None = None) -> CommandResult:
        """An edit of the selected corner or segment: radius, sharp, fillet, axis, delete, close."""

        from openretop.modeling import profile_edit

        session = self._session_for("section")
        if isinstance(session, CommandResult):
            return session
        if session.section_profiles is None or session.section_selected is None:
            return CommandResult.failure("Pick a corner or a segment of the profile first.")
        kind, loop, index = session.section_selected
        profile = session.section_profiles[loop]
        before = copy.deepcopy(session.section_profiles)
        try:
            if operation == "radius":
                if kind != "segment":
                    raise ValueError("pick the arc to change")
                profile_edit.set_arc_radius(profile, index, float(value or 0.0))
                status = f"Radius {float(value or 0.0):g}"
            elif operation == "sharp":
                if kind != "segment":
                    raise ValueError("pick the arc to take out")
                profile_edit.make_sharp(profile, index)
                session.section_selected = None
                status = "Sharp corner"
            elif operation == "fillet":
                if kind != "vertex":
                    raise ValueError("pick the corner to round")
                arc = profile_edit.add_fillet(profile, index, float(value or 0.0))
                session.section_selected = ("segment", loop, arc)
                status = f"Rounded with R{float(value or 0.0):g}"
            elif operation == "axis":
                if kind != "segment":
                    raise ValueError("pick the line to straighten")
                status = f"Line made {profile_edit.make_axis_line(profile, index)}"
            elif operation == "delete":
                if kind != "segment":
                    raise ValueError("pick the segment to delete")
                profile_edit.delete_segment(profile, index)
                session.section_selected = None
                status = "Segment deleted: its neighbours meet"
            elif operation == "close":
                status = profile_edit.close_profile(profile).capitalize()
                session.section_selected = None
            else:
                raise ValueError(f"unknown edit: {operation}")
        except (ValueError, IndexError) as error:
            session.section_profiles = before
            return CommandResult.failure(str(error).capitalize())
        self._remeasure(loop)
        return self._profile_changed("Edit Sketch Profile", before, f"{status}; deviation max {profile.deviation:.3f} {self.state.units}")

    def _remeasure(self, loop: int) -> None:
        """The profile's deviation from its section loop, after an edit."""

        session = self.session
        if session is None or session.section_profiles is None:
            return
        outlines = self._section_outlines()
        profile = session.section_profiles[loop]
        if loop < len(outlines) and profile.segments:
            distances = profile.distances(outlines[loop])
            profile.deviation = float(np.max(distances))
            profile.rms = float(np.sqrt(np.mean(distances**2)))

    def _profile_changed(self, name: str, before: list[Profile2D], status: str) -> CommandResult:
        """An undo step for an edit of the profile in the tool (not yet part of the model)."""

        session = self.session
        assert session is not None
        after = copy.deepcopy(session.section_profiles) or []

        def restore(profiles: list[Profile2D]) -> None:
            if self.session is not None and self.session.tool == "section":
                self.session.section_profiles = copy.deepcopy(profiles)
                self.session.section_selected = None

        payload = CallbackUndoPayload(name, undo_action=lambda: restore(before), redo_action=lambda: restore(after))
        return CommandResult.ok(status=status, changed=True, undo_payload=payload)

    # -- Extrude -------------------------------------------------------------------------------

    def _extrude_profile_entity(self) -> ModelEntity | None:
        model = self.state.model
        profiles = [entity for entity in model.entities if entity.kind == "profile"]
        selected = [entity for entity in profiles if entity.id in model.selected_ids]
        if selected:
            return selected[-1]
        current = None if self.session is None else model.get(self.session.extrude_profile)
        if current is not None and current.kind == "profile":
            return current
        visible = [entity for entity in profiles if entity.visible]
        candidates = visible or profiles
        return candidates[-1] if candidates else None

    def extrude_measure(self) -> CommandResult:
        """Depths from the scan: how far the sketch's walls run either side of its plane."""

        session = self._session_for("extrude")
        if isinstance(session, CommandResult):
            return session
        profile = self.state.model.get(session.extrude_profile)
        if profile is None or self.state.mesh_object is None:
            return CommandResult.failure("Needs a sketch and the scan.")
        from openretop.modeling.feature_depth import loop_depths

        points, normals = self._world_scan_points(MAX_KERNEL_SCAN_POINTS)
        spacing = self._scan_spacing()
        tolerance = float(profile.params.get("tolerance", 0.05))
        depths = loop_depths(points, normals, profile.params["frame"], self._extrude_loops(profile), band=max(4.0 * tolerance, 0.5 * spacing), step=spacing)
        outer = [depth for depth in depths if depth.found and depth.depth % 2 == 0]
        if not outer:
            session.extrude_holes = {}
            return CommandResult.ok(status="No wall found in the scan along the sketch: set the depth by hand.", changed=True)
        session.extrude_front = round(max(0.0, max(depth.high for depth in outer)), 4)
        session.extrude_back = round(max(0.0, -min(depth.low for depth in outer)), 4)
        session.extrude_holes = {index: (depth.low, depth.high) for index, depth in enumerate(depths) if depth.found and depth.depth % 2}
        session.preview = None
        units = self.state.units
        pockets = "".join(f"; hole {index + 1}: {low:.3f} to {high:.3f}" for index, (low, high) in session.extrude_holes.items())
        return CommandResult.ok(
            status=f"Depth from the scan: {session.extrude_front:.3f} ahead, {session.extrude_back:.3f} behind {units}{pockets}.",
            changed=True,
        )

    def extrude_ranges(self) -> list[tuple[float, float]]:
        """Per loop of the sketch: (low, high) along its normal."""

        session = self.session
        profile = None if session is None else self.state.model.get(session.extrude_profile)
        if session is None or profile is None:
            return []
        low, high = -session.extrude_back, session.extrude_front
        ranges = []
        for index, _loop in enumerate(self._extrude_loops(profile)):
            hole = session.extrude_holes.get(index) if session.extrude_auto else None
            ranges.append((max(low, hole[0]), min(high, hole[1])) if hole is not None else (low, high))
        return ranges

    def _extrude_job(self) -> KernelReply | CommandResult:
        session = self._session_for("extrude")
        if isinstance(session, CommandResult):
            return session
        profile = self.state.model.get(session.extrude_profile)
        if profile is None:
            return CommandResult.failure("The sketch to extrude is gone.")
        if session.extrude_front + session.extrude_back <= 0.0:
            return CommandResult.failure("Give the extrusion some depth (ahead, behind or both).")
        target = self.state.model.get(session.extrude_target) if session.extrude_mode != "new" else None
        if session.extrude_mode != "new" and target is None:
            return CommandResult.failure("Add and Cut need a body: make one first (New body), or pick one in the tree.")
        loops = self._extrude_loops(profile)
        if not loops:
            return CommandResult.failure("The picked region is gone from the sketch: pick again.")
        return self.worker.call(
            "extrude",
            profile.params["frame"],
            loops,
            self.extrude_ranges(),
            draft=session.extrude_draft,
            mode=session.extrude_mode,
            target=None if target is None else target.brep,
        )

    def extrude_preview(self) -> CommandResult:
        reply = self._extrude_job()
        if isinstance(reply, CommandResult):
            return reply
        if not reply.ok:
            return _kernel_failure("Extrude failed", reply)
        session = self.session
        assert session is not None
        session.preview = reply.value
        valid = "" if reply.value.get("solid") else " (not a valid solid: check the sketch)"
        return CommandResult.ok(status=f"Extrude: volume {reply.value['volume']:.1f} {self.state.units}^3{valid}. Create keeps it.", changed=True)

    def extrude_apply(self) -> CommandResult:
        reply = self._extrude_job()
        if isinstance(reply, CommandResult):
            return reply
        if not reply.ok:
            return _kernel_failure("Extrude failed", reply)
        session = self.session
        assert session is not None
        model = self.state.model
        before = model.snapshot()
        mode = session.extrude_mode
        params = {
            "profile": session.extrude_profile,
            "mode": session.extrude_mode,
            "front": session.extrude_front,
            "back": session.extrude_back,
            "draft": session.extrude_draft,
            "ranges": [list(item) for item in self.extrude_ranges()],
        }
        target = model.get(session.extrude_target) if session.extrude_mode != "new" else None
        sources = (session.extrude_profile,) + (() if target is None else (target.id,))
        timeline = model.timeline
        sketch_feature = timeline.maker(session.extrude_profile)
        if sketch_feature is None:  # a sketch from before the history: it starts one now
            profile_entity = model.get(session.extrude_profile)
            assert profile_entity is not None
            sketch_feature = timeline.add("sketch", profile_entity.id, dict(profile_entity.params))
        if target is not None and not timeline.body_features(target.id):
            # a body the history did not make (sewn in Surface, or older): kept as it is now
            timeline.add("base", target.id, {"brep": target.brep, "kind": target.kind})
        if target is not None:  # the body changes and keeps its id: features further on refer to it
            entity = replace_entity(model, target.id, reply.value, tool="extrude", params=params)
            entity.sources = sources
            model.revision += 1
        else:
            entity = entity_from_result(model, reply.value, tool="extrude", params=params, sources=sources)
            model.add(entity)
        timeline.add(
            "extrude",
            entity.id,
            {
                "sketch": sketch_feature.id,
                "mode": mode,
                "front": float(session.extrude_front),
                "back": float(session.extrude_back),
                "draft": float(session.extrude_draft),
                "auto": bool(session.extrude_auto),
                "holes": {str(index): [float(low), float(high)] for index, (low, high) in session.extrude_holes.items()},
                "regions": list(session.extrude_regions),
            },
            result=reply.value,
        )
        profile = model.get(session.extrude_profile)
        if profile is not None:
            profile.visible = False  # used: out of the way, as in CAD
        model.selected_ids = [entity.id]
        session.preview = None
        session.extrude_target = entity.id
        session.extrude_mode = "add"  # a further sketch most likely adds to (or cuts) this body
        verb = {"new": "Created", "add": "Added to", "cut": "Cut from"}[mode]
        return self._changed("Extrude", before, f"{verb} {entity.name}: volume {reply.value['volume']:.1f} {self.state.units}^3")

    def _extrude_loops(self, profile: ModelEntity) -> list[dict[str, Any]]:
        """The loops an extrude takes: all of the sketch, or a 3D Sketch's picked regions."""

        session = self.session
        regions = [] if session is None else session.extrude_regions
        if not regions or "sketch2d" not in profile.params:
            return list(profile.params.get("loops", []))
        from openretop.modeling.sketch2d import Sketch2D
        from openretop.modeling.sketch_profiles import find_profiles

        return find_profiles(Sketch2D.from_dict(profile.params["sketch2d"])).loops_for(regions) or []

    def extrude_pick_region(self, world_point: object) -> CommandResult:
        """A click on a 3D Sketch's plane during Extrude: add or remove the region there
        (none picked: the whole sketch extrudes)."""

        session = self._session_for("extrude")
        if isinstance(session, CommandResult):
            return session
        profile = self.state.model.get(session.extrude_profile)
        if profile is None or "sketch2d" not in profile.params:
            return CommandResult.ok(status="This sketch extrudes whole (pick regions in a 3D Sketch).")
        from openretop.cad_kernel.profiles import PlaneFrame
        from openretop.modeling.sketch2d import Sketch2D
        from openretop.modeling.sketch_profiles import find_profiles

        frame = PlaneFrame.from_dict(profile.params["frame"])
        point = frame.to_plane(world_point)[0]
        region = find_profiles(Sketch2D.from_dict(profile.params["sketch2d"])).region_at(point)
        if region is None:
            return CommandResult.ok(status="No closed region there.")
        if region.key in session.extrude_regions:
            session.extrude_regions.remove(region.key)
        else:
            session.extrude_regions.append(region.key)
        session.extrude_holes = {}  # measured for the loops as they were
        session.preview = None
        picked = len(session.extrude_regions)
        self.extrude_preview()
        return CommandResult.ok(status=f"{picked} region(s) picked" if picked else "All regions (none picked)", changed=True)

    def extrude_region_outlines(self) -> list[np.ndarray]:
        """The picked regions' outlines (world), to show them."""

        session = self.session
        profile = None if session is None else self.state.model.get(session.extrude_profile)
        if session is None or profile is None or not session.extrude_regions or "sketch2d" not in profile.params:
            return []
        from openretop.cad_kernel.profiles import PlaneFrame
        from openretop.modeling.sketch2d import Sketch2D
        from openretop.modeling.sketch_profiles import find_profiles

        frame = PlaneFrame.from_dict(profile.params["frame"])
        profiles = find_profiles(Sketch2D.from_dict(profile.params["sketch2d"]))
        outlines = []
        for key in session.extrude_regions:
            region = profiles.region(key)
            if region is not None:
                outlines.append(frame.to_world(region.outer.polyline(24)))
        return outlines

    # -- 3D Sketch (P-03) ------------------------------------------------------------------------

    def _sketch2d(self) -> SketchMode | CommandResult:
        session = self._session_for("plane_sketch")
        if isinstance(session, CommandResult):
            return session
        assert session.sketch2d is not None
        return session.sketch2d

    def _sketch2d_change(self, name: str, change: Any) -> CommandResult:
        """Run ``change(mode)`` (returns a status, or a SolveReport) as one undo step of the tool."""

        mode = self._sketch2d()
        if isinstance(mode, CommandResult):
            return mode
        before = mode.sketch.to_dict()
        outcome = change(mode)
        if hasattr(outcome, "ok"):
            if not outcome.ok:
                return CommandResult.failure(outcome.message, status=outcome.message)
            status = outcome.message
        else:
            status = str(outcome)
        after = mode.sketch.to_dict()
        if after == before:
            return CommandResult.ok(status=status, changed=True)
        from openretop.modeling.sketch2d import Sketch2D

        def restore(data: dict[str, Any]) -> None:
            session = self.session
            if session is not None and session.tool == "plane_sketch" and session.sketch2d is not None:
                session.sketch2d.sketch = Sketch2D.from_dict(data)
                session.sketch2d.end_shape()
                session.sketch2d.selected.clear()

        payload = CallbackUndoPayload(name, undo_action=lambda: restore(before), redo_action=lambda: restore(after))
        dof = mode.sketch.dof()
        defined = "fully defined" if dof == 0 else f"{dof} degree(s) of freedom"
        return CommandResult.ok(status=f"{status} - {defined}", changed=True, undo_payload=payload)

    def _sketch2d_reference(self) -> None:
        """The scan's cut on the sketch plane, shown to draw over (cached per plane)."""

        session = self.session
        if session is None or session.sketch2d is None or self.state.mesh_object is None:
            return
        from openretop.geometry.sections import extract_section_by_plane

        mode = session.sketch2d
        source = self.transform.transformed_source_mesh()
        key = (mode.plane, round(mode.offset, 9), id(source.vertices), len(source.vertices))
        if session.sketch2d_reference_key == key:
            return
        axis = np.asarray(SKETCH_PLANES[mode.plane][2])
        section = extract_section_by_plane(source, axis * mode.offset, axis)
        session.sketch2d_reference = [np.asarray(poly.points, dtype=float) for poly in section.polylines if poly.point_count >= 2]
        session.sketch2d_reference_key = key

    def sketch2d_set_plane(self, plane: str | None, *, offset: float | None = None) -> CommandResult:
        mode = self._sketch2d()
        if isinstance(mode, CommandResult):
            return mode
        plane = plane or mode.plane
        if plane not in SKETCH_PLANES:
            return CommandResult.failure(f"Unknown plane: {plane}")
        if plane != mode.plane and mode.sketch.curves:
            return CommandResult.failure("The sketch has geometry on this plane: finish it, or start a new 3D Sketch for another plane.")
        if plane != mode.plane and offset is None:
            offset = self._scan_center(plane)
        mode.plane = plane
        if offset is not None:
            mode.offset = float(offset)
        self._sketch2d_reference()
        units = self.state.units
        return CommandResult.ok(status=f"3D Sketch on {plane} at {mode.offset:.3f} {units}", changed=True)

    def sketch2d_tool(self, tool: str) -> CommandResult:
        mode = self._sketch2d()
        if isinstance(mode, CommandResult):
            return mode
        try:
            mode.set_tool(tool)
        except ValueError as error:
            return CommandResult.failure(str(error))
        hints = {
            "select": "Select: click points and curves (Ctrl adds); drag a point to move it.",
            "line": "Line: click points; click the first one to close; Enter ends.",
            "rectangle": "Rectangle: click two opposite corners.",
            "circle": "Circle: click the centre, then a point on it.",
            "arc": "Arc: click the centre, the start, then the end (counter-clockwise).",
        }
        return CommandResult.ok(status=hints[tool], changed=True)

    def sketch2d_click(self, world_point: object, *, snap: float, add: bool = False) -> CommandResult:
        mode = self._sketch2d()
        if isinstance(mode, CommandResult):
            return mode
        xy = mode.to_plane(world_point)
        if mode.tool == "select":
            status = mode.click(xy, snap, add=add)
            return CommandResult.ok(status=status, changed=True)
        return self._sketch2d_change(f"Sketch {mode.tool.title()}", lambda m: m.click(xy, snap, add=add))

    def sketch2d_hover(self, world_point: object | None) -> CommandResult:
        mode = self._sketch2d()
        if isinstance(mode, CommandResult):
            return mode
        mode.hover = None if world_point is None else mode.to_plane(world_point)
        return CommandResult.ok(changed=bool(mode.pending))

    def sketch2d_end_shape(self) -> CommandResult:
        mode = self._sketch2d()
        if isinstance(mode, CommandResult):
            return mode
        drawing = bool(mode.pending)
        mode.end_shape()
        return CommandResult.ok(status="Shape ended" if drawing else "", changed=drawing)

    def sketch2d_drag(self, point_id: str, world_point: object, *, before: dict[str, Any] | None = None) -> CommandResult:
        """Drag a point (live); with ``before`` (the sketch when the drag began) the drag
        ends and becomes one undo step."""

        mode = self._sketch2d()
        if isinstance(mode, CommandResult):
            return mode
        if point_id not in mode.sketch.points:
            return CommandResult.failure("That point is gone.")
        report = mode.drag(point_id, mode.to_plane(world_point))
        if before is None:
            return CommandResult.ok(changed=True)
        from openretop.modeling.sketch2d import Sketch2D

        after = mode.sketch.to_dict()

        def restore(data: dict[str, Any]) -> None:
            session = self.session
            if session is not None and session.tool == "plane_sketch" and session.sketch2d is not None:
                session.sketch2d.sketch = Sketch2D.from_dict(data)

        payload = CallbackUndoPayload("Drag Sketch Point", undo_action=lambda: restore(before), redo_action=lambda: restore(after))
        return CommandResult.ok(status="Moved" if report.ok else "That point is held where it is", changed=True, undo_payload=payload)

    def sketch2d_select(self, ids: list[str]) -> CommandResult:
        mode = self._sketch2d()
        if isinstance(mode, CommandResult):
            return mode
        mode.select(ids)
        return CommandResult.ok(status=f"{len(mode.selected)} selected", changed=True)

    def sketch2d_constrain(self, kind: str) -> CommandResult:
        return self._sketch2d_change(kind.replace("_", " ").title(), lambda m: m.constrain(kind))

    def sketch2d_dimension(self, value: float | None = None, kind: str | None = None) -> CommandResult:
        return self._sketch2d_change("Dimension", lambda m: m.dimension(value, kind))

    def sketch2d_set_dimension(self, constraint_id: str, value: float) -> CommandResult:
        return self._sketch2d_change("Change Dimension", lambda m: m.set_dimension(constraint_id, value))

    def sketch2d_delete_constraint(self, constraint_id: str) -> CommandResult:
        def change(mode: SketchMode) -> str:
            mode.delete_constraint(constraint_id)
            return "Constraint deleted"

        return self._sketch2d_change("Delete Constraint", change)

    def sketch2d_delete(self) -> CommandResult:
        def change(mode: SketchMode) -> str:
            count = mode.delete_selected()
            return f"Deleted {count} item(s)" if count else "Select points or curves to delete"

        return self._sketch2d_change("Delete Sketch Items", change)

    def sketch2d_construction(self) -> CommandResult:
        def change(mode: SketchMode) -> str:
            count = mode.toggle_construction()
            return f"{count} curve(s) switched construction / normal" if count else "Select curves first"

        return self._sketch2d_change("Construction", change)

    def sketch2d_finish(self) -> CommandResult:
        """Keep the sketch: a profile (its regions as faces, open curves as wires) and a
        history feature. Editing a sketch updates it and rebuilds what was made from it."""

        mode = self._sketch2d()
        if isinstance(mode, CommandResult):
            return mode
        from openretop.modeling.sketch_profiles import find_profiles

        mode.end_shape()
        loops = find_profiles(mode.sketch).all_loops()
        if not loops:
            message = "Draw something first (or close the tool to leave without a sketch)."
            return CommandResult.failure(message, status=message)
        frame = mode.frame()
        reply = self.worker.call("profile", frame, loops)
        if not reply.ok:
            return _kernel_failure("Sketch failed", reply)
        params = {
            "plane": mode.plane,
            "offset": mode.offset,
            "frame": frame,
            "loops": loops,
            "tolerance": 0.05,
            "sketch2d": mode.sketch.to_dict(),
        }
        model = self.state.model
        editing = model.get(mode.editing) if mode.editing else None
        self.session = None  # the tool closes, as Fusion's Finish Sketch
        if editing is None:
            entity = entity_from_result(model, reply.value, tool="sketch2d", params=params, name=model.next_name("3D Sketch"))
            added = self._add_entities([entity], name="3D Sketch")
            if added.success:
                model.timeline.add("sketch", entity.id, params, result=reply.value)
            return added
        before = model.snapshot()
        replace_entity(model, editing.id, reply.value, tool="sketch2d", params=params)
        model.selected_ids = [editing.id]
        feature = model.timeline.maker(editing.id)
        if feature is None:
            model.timeline.add("sketch", editing.id, params, result=reply.value)
            return self._changed("Edit 3D Sketch", before, f"Updated {editing.name}")
        feature.inputs = dict(params)
        feature.result = reply.value
        feature.status, feature.message = "ok", ""
        later = model.timeline.features[model.timeline.index(feature.id) + 1 :]
        if not any(feature.id in item.reads() for item in later):
            model.revision += 1
            return self._changed("Edit 3D Sketch", before, f"Updated {editing.name}")
        report = regenerate(model, self.worker, later[0].id)
        return self._changed("Edit 3D Sketch", before, f"Updated {editing.name}. {report.summary()}")

    def sketch2d_edit(self, entity_id: str) -> CommandResult:
        """Reopen a finished 3D Sketch for editing."""

        entity = self.state.model.get(entity_id)
        if entity is None or "sketch2d" not in entity.params:
            return CommandResult.failure("Select a 3D Sketch to edit.")
        started = self.start("plane_sketch")
        if not started.success:
            return started
        session = self.session
        assert session is not None and session.sketch2d is not None
        from openretop.modeling.sketch2d import Sketch2D

        params = entity.params
        session.sketch2d = SketchMode(Sketch2D.from_dict(params["sketch2d"]), str(params.get("plane", "XY")), float(params.get("offset", 0.0)))
        session.sketch2d.editing = entity.id
        session.sketch2d.tool = "select"
        self._sketch2d_reference()
        return CommandResult.ok(status=f"Editing {entity.name}: change dimensions, drag points, draw more; Finish Sketch updates it.", changed=True)

    def sketch2d_plane_outline(self) -> np.ndarray | None:
        """A rectangle on the sketch plane around the scan's cut and the sketch (world)."""

        session = self.session
        if session is None or session.sketch2d is None:
            return None
        mode = session.sketch2d
        local = [mode.to_plane(point) for line in session.sketch2d_reference for point in line[:: max(1, len(line) // 200)]]
        local.extend(mode.sketch.position(point) for point in mode.sketch.points)
        if local:
            xy = np.asarray(local)
            low, high = xy.min(axis=0), xy.max(axis=0)
        else:
            low, high = np.array([-50.0, -50.0]), np.array([50.0, 50.0])
        margin = max(0.15 * float(np.max(high - low)), 10.0)
        low, high = low - margin, high + margin
        corners = np.array([[low[0], low[1]], [high[0], low[1]], [high[0], high[1]], [low[0], high[1]], [low[0], low[1]]])
        return mode.to_world(corners)

    def sketch2d_view_world(self) -> dict[str, Any] | None:
        """The sketch as the viewport draws it: polylines and points in world coordinates."""

        session = self.session
        if session is None or session.tool != "plane_sketch" or session.sketch2d is None:
            return None
        mode = session.sketch2d
        view = mode.view()
        for curve in view["curves"]:
            curve["world"] = mode.to_world(curve["points"])
        for point in view["points"]:
            point["world"] = mode.to_world(point["xy"])[0]
        for label in view["labels"]:
            label["world"] = mode.to_world(label["xy"])[0]
        view["preview_world"] = None if view["preview"] is None else mode.to_world(view["preview"])
        view["reference"] = list(session.sketch2d_reference)
        view["frame"] = mode.frame()
        return view

    # -- history (P-01) ------------------------------------------------------------------------

    def edit_feature(self, feature_id: str, **changes: Any) -> CommandResult:
        """Change a feature's inputs (an extrude's depths, draft or mode) and replay the
        history from it."""

        model = self.state.model
        feature = model.timeline.get(feature_id)
        if feature is None:
            return CommandResult.failure("That feature is no longer in the history.")
        editable = {"extrude": {"front", "back", "draft", "mode", "auto"}}.get(feature.kind, set())
        unknown = set(changes) - editable
        if unknown:
            return CommandResult.failure(f"{feature.name} has no {', '.join(sorted(unknown))} to change.")
        if "mode" in changes and changes["mode"] not in EXTRUDE_MODES:
            return CommandResult.failure(f"Unknown extrude mode: {changes['mode']}")
        before = model.snapshot()
        feature.inputs.update(changes)
        report = regenerate(model, self.worker, feature.id)
        return self._changed(f"Edit {feature.name}", before, report.summary())

    def rebuild(self) -> CommandResult:
        """Replay the whole history (after opening a project, or to check it)."""

        model = self.state.model
        if not model.timeline.features:
            return CommandResult.ok(status="Nothing to rebuild: the model has no history.")
        before = model.snapshot()
        report = regenerate(model, self.worker)
        return self._changed("Rebuild", before, report.summary())

    def _scan_spacing(self) -> float:
        """The scan's typical point spacing (median edge length)."""

        source = self.transform.transformed_source_mesh()
        triangles = np.asarray(source.triangles)[:20000]
        vertices = np.asarray(source.vertices, dtype=float)
        if len(triangles) == 0:
            return 1.0
        edges = vertices[triangles[:, [1, 2, 0]]] - vertices[triangles]
        return float(np.median(np.linalg.norm(edges, axis=2))) or 1.0

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
        """A surface through two or more sketch curves (Surface Sketch or Cut Section), in order."""

        ids = curve_ids if curve_ids is not None else tuple(self.state.model.selected_curve_ids)
        sketch = self.state.model.sketch
        curves = [curve for curve in (sketch.curve(value) for value in ids) if curve is not None]
        if len(curves) < 2:
            return CommandResult.failure("Select two or more curves to loft between (click them; Ctrl+click adds).")
        if any(curve.closed for curve in curves) and not all(curve.closed for curve in curves):
            return CommandResult.failure("Loft between curves that are all open or all closed.")
        reply = self.worker.call("loft", [curve.polyline for curve in curves], ruled=ruled)
        if not reply.ok:
            return _kernel_failure("Loft failed", reply)
        entity = entity_from_result(self.state.model, reply.value, tool="loft", params={"sketch_curves": [curve.id for curve in curves], "ruled": ruled})
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
        if self.state.model.sketch.curve(curve_id) is None:
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
                curve = self.state.model.sketch.curve(side["curve"])
                if curve is None:
                    return CommandResult.failure("A boundary curve was deleted; clear the boundary and pick again.")
                boundaries.append({"points": curve.polyline, "continuity": "contact"})
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

    # -- Resize handles ------------------------------------------------------------------------

    def handle_entity(self) -> ModelEntity | None:
        """The surface whose sides show drag arrows: the one selected surface, with no tool open
        (or in Fit Surface or Extend)."""

        if self.tool not in (None, "fit_surface", "extend"):
            return None
        model = self.state.model
        if len(model.selected_ids) != 1:
            return None
        entity = model.get(model.selected_ids[0])
        if entity is None or entity.is_body or not entity.visible:
            return None
        return entity

    def surface_handles(self, entity_id: str) -> dict[str, Any]:
        """The draggable sides of a surface (cached until it changes): for each, its edge,
        midpoint and outward direction. A trimmed surface has none."""

        entity = self.state.model.get(entity_id)
        if entity is None:
            return {"rectangular": False, "handles": []}
        key = (entity.id, id(entity.brep))
        if self._handles is not None and self._handles[0] == key:
            return self._handles[1]
        reply = self.worker.call("face_handles", entity.brep)
        value: dict[str, Any] = dict(reply.value) if reply.ok else {"rectangular": False, "handles": [], "reason": reply.error}
        value["handles"] = [
            {name: (item if name == "side" else np.asarray(item, dtype=float)) for name, item in handle.items()} for handle in value["handles"]
        ]
        value["corners"] = [
            {
                "sides": tuple(corner["sides"]),
                "point": np.asarray(corner["point"], dtype=float),
                "directions": tuple(np.asarray(direction, dtype=float) for direction in corner["directions"]),
            }
            for corner in value.get("corners", [])
        ]
        self._handles = (key, value)
        return value

    def resize_surface(self, entity_id: str, changes: dict[str, float]) -> CommandResult:
        """Move a surface's sides along it: positive grows (an analytic surface continues
        exactly, a freeform one along its edge tangents), negative cuts it back."""

        model = self.state.model
        entity = model.get(entity_id)
        if entity is None or entity.is_body:
            return CommandResult.failure("Select a surface to resize.")
        changes = {str(side): float(value) for side, value in changes.items() if abs(float(value)) > 0}
        if not changes:
            return CommandResult.ok(status="Nothing to change")
        reply = self.worker.call("resize", entity.brep, changes, kind=entity.kind)
        if not reply.ok:
            return _kernel_failure(f"Resizing {entity.name} failed", reply)
        before = model.snapshot()
        fresh = entity_from_result(model, reply.value, tool=entity.tool, params=entity.params, sources=entity.sources)
        fresh.id, fresh.name, fresh.color, fresh.visible, fresh.kind = entity.id, entity.name, entity.color, entity.visible, entity.kind
        fresh.stats = {**entity.stats, "area": reply.value.get("area", entity.stats.get("area"))}  # the fit to the scan is unchanged
        model.entities[model.entities.index(entity)] = fresh
        model.revision += 1
        units = self.state.units
        moved = ", ".join(f"{side} {'+' if value > 0 else ''}{value:.3f}" for side, value in changes.items())
        return self._changed("Resize Surface", before, f"Resized {entity.name} ({moved} {units})")

    # -- Trim ----------------------------------------------------------------------------------

    def trim_compute(self) -> CommandResult:
        session = self._session_for("trim")
        if isinstance(session, CommandResult):
            return session
        # two or more selected surfaces trim each other; one selected is cut by the cut lines
        # alone; otherwise every visible surface takes part (fit several, then Trim)
        selected = session.trim_selected
        use_selected = len(selected) >= 2 or (len(selected) == 1 and bool(session.trim_cuts))
        ids = selected if use_selected else session.trim_sources
        sources = [entity for entity in (self.state.model.get(value) for value in ids) if entity is not None]
        session.trim_used = tuple(entity.id for entity in sources)
        if not sources or (len(sources) < 2 and not session.trim_cuts):
            return CommandResult.failure("Trimming needs two surfaces, or a cut line drawn across one (Cut Line).")
        if self.state.mesh_object is not None:
            vertices, normals = self._world_scan_points(MAX_KERNEL_SCAN_POINTS)
        else:
            vertices, normals = np.zeros((0, 3)), np.zeros((0, 3))
        reply = self.worker.call(
            "trim",
            [entity.brep for entity in sources],
            vertices,
            normals,
            tolerance=session.trim_tolerance,
            overlap=session.trim_overlap,
            cuts=session.trim_cuts,
            manual=session.trim_manual,
        )
        if not reply.ok:
            return _kernel_failure("Trim failed", reply)
        pieces = reply.value["pieces"]
        for piece in pieces:
            piece["source_id"] = sources[int(piece["source"])].id
        session.trim_pieces = pieces
        kept = sum(1 for piece in pieces if piece["keep"])
        why = "all kept: click the pieces to cut away" if session.trim_manual or self.state.mesh_object is None else f"{kept} kept (on the scan)"
        return CommandResult.ok(
            status=f"{len(pieces)} pieces, {why}. Click a piece to keep or drop it, then Apply.",
            changed=True,
        )

    def trim_start_cut(self) -> CommandResult:
        """Draw a cut line: clicks on the surfaces (or the scan) place its points; it cuts
        along the view direction it is drawn in, clean through, like a knife."""

        session = self._session_for("trim")
        if isinstance(session, CommandResult):
            return session
        session.trim_drawing, session.trim_cut, session.trim_cut_direction = True, [], None
        return CommandResult.ok(status="Cut Line: click points across the surface, Enter cuts, Esc cancels.", changed=True)

    def trim_cut_point(self, world_point: object, view_direction: object) -> CommandResult:
        session = self._session_for("trim")
        if isinstance(session, CommandResult):
            return session
        if not session.trim_drawing:
            return CommandResult.failure("Start a cut line first (Cut Line).")
        session.trim_cut.append(np.asarray(world_point, dtype=float).reshape(3))
        if session.trim_cut_direction is None:
            session.trim_cut_direction = np.asarray(view_direction, dtype=float).reshape(3)
        count = len(session.trim_cut)
        return CommandResult.ok(status=f"Cut line: {count} point(s)" + (", Enter cuts" if count >= 2 else ""), changed=True)

    def trim_finish_cut(self) -> CommandResult:
        """End the cut line and split the surfaces along it."""

        session = self._session_for("trim")
        if isinstance(session, CommandResult):
            return session
        points, direction = session.trim_cut, session.trim_cut_direction
        session.trim_drawing, session.trim_cut, session.trim_cut_direction = False, [], None
        if len(points) < 2 or direction is None:
            return CommandResult.ok(status="Cut line cancelled (it needs two points)", changed=True)
        session.trim_cuts.append({"points": np.vstack(points), "direction": direction})
        return self.trim_compute()

    def trim_cancel_cut(self) -> CommandResult:
        session = self._session_for("trim")
        if isinstance(session, CommandResult):
            return session
        session.trim_drawing, session.trim_cut, session.trim_cut_direction = False, [], None
        return CommandResult.ok(status="Cut line cancelled", changed=True)

    def trim_clear_cuts(self) -> CommandResult:
        session = self._session_for("trim")
        if isinstance(session, CommandResult):
            return session
        session.trim_cuts, session.trim_pieces = [], None
        session.trim_drawing, session.trim_cut, session.trim_cut_direction = False, [], None
        return CommandResult.ok(status="Cut lines cleared", changed=True)

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
        session.trim_cuts = []  # applied: the next trim starts afresh
        kept = [piece for piece in session.trim_pieces if piece["keep"]]
        if not kept:
            return CommandResult.failure("No piece is kept: click pieces to keep them.")
        sources = tuple(dict.fromkeys(piece["source_id"] for piece in kept))
        sew = sew and len(sources) > 1  # sewing joins surfaces: one trimmed surface stays a surface
        params = {
            "tolerance": session.trim_tolerance,
            "overlap": session.trim_overlap,
            "sources": list(session.trim_used or session.trim_sources),
            "manual": session.trim_manual,
            "cuts": [{"points": cut["points"].tolist(), "direction": cut["direction"].tolist()} for cut in session.trim_cuts],
        }
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
        for source_id in session.trim_used or session.trim_sources:  # hidden, not deleted: trimming again stays possible
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
        self.state.model.selected_feature = ""
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
        reply = self.worker.call(
            "export", [entity.brep for entity in targets], str(path), file_format=file_format, units=self.state.units
        )
        if not reply.ok:
            return _kernel_failure("Export failed", reply)
        info = reply.value
        warnings: tuple[str, ...] = ()
        if info["faces_back"] != info["faces"]:
            warnings = (f"The file reads back with {info['faces_back']} faces instead of {info['faces']}.",)
        return CommandResult.ok(
            status=f"Exported {len(targets)} item(s), {info['faces']} faces, in {self.state.units}, to {path}", warnings=warnings
        )

    # -- Surface Sketch -------------------------------------------------------------------------------

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
        key = placed.tobytes() + repr((session.sketch_smoothness, session.sketch_feature)).encode()
        if self._placed_line is None or self._placed_line[0] != key:
            line = (
                curve_on_mesh(placed, projector, smoothness=session.sketch_smoothness, feature=session.sketch_feature)
                if len(placed) >= 2
                else placed.copy()
            )
            self._placed_line = (key, line)
        line = self._placed_line[1]
        if session.hover is None:
            return line if len(line) >= 2 else None
        span = curve_on_mesh(np.vstack([placed[-1], session.hover]), projector, smoothing=0, feature=session.sketch_feature)
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
        curve = sketch.add_curve(nodes, projector, closed=close, smoothness=session.sketch_smoothness, feature=session.sketch_feature)
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

    # -- editing curves and points ---------------------------------------------------------

    def sketch_select_node(self, node_id: str | None) -> CommandResult:
        session = self._session_for("sketch")
        if isinstance(session, CommandResult):
            return session
        sketch = self.state.model.sketch
        session.selected_node = node_id if node_id in sketch.nodes else None
        if session.selected_node is None:
            return CommandResult.ok(status="No point selected", changed=True)
        curves = [curve.name for curve in sketch.curves if session.selected_node in curve.nodes]
        return CommandResult.ok(
            status=f"Point on {', '.join(curves) or 'no curve'}: drag to move, Delete removes it, right-click for more (split here ...).",
            changed=True,
        )

    def _sketch_edit(self, name: str, change: Any) -> CommandResult:
        """Run an edit of the sketch as one undo step (``change`` returns the status)."""

        projector = self.sketch_projector()
        if projector is None:
            return CommandResult.failure("Open a scan first.")
        before = self.state.model.snapshot()
        try:
            status = change(self.state.model.sketch, projector)
        except ValueError as error:
            return CommandResult.failure(str(error))
        self.state.model.revision += 1
        return self._changed(name, before, status)

    def sketch_insert_point(self, curve_id: str, world_point: object) -> CommandResult:
        """A new point on a curve where it passes ``world_point``: drag it to reshape the curve."""

        def change(sketch: Any, projector: MeshProjector) -> str:
            node = sketch.insert_node(curve_id, world_point, projector)
            if self.session is not None:
                self.session.selected_node = node
            return "Point added: drag it to reshape the curve"

        return self._sketch_edit("Add Sketch Point", change)

    def sketch_delete_point(self, node_id: str | None = None) -> CommandResult:
        session = self.session
        node = node_id or (session.selected_node if session is not None else None)
        if node is None or node not in self.state.model.sketch.nodes:
            return CommandResult.failure("Select a point first (click it).")

        def change(sketch: Any, projector: MeshProjector) -> str:
            touched = sketch.remove_node(node, projector)
            if session is not None:
                session.selected_node = None
            known = {curve.id for curve in sketch.curves}
            self.state.model.selected_curve_ids = [value for value in self.state.model.selected_curve_ids if value in known]
            return f"Point removed ({touched} curve(s) changed)"

        return self._sketch_edit("Delete Sketch Point", change)

    def sketch_split(self, node_id: str | None = None, curve_id: str | None = None) -> CommandResult:
        """Cut the curve(s) through a point there: an open curve in two, a closed one opened."""

        session = self.session
        node = node_id or (session.selected_node if session is not None else None)
        sketch = self.state.model.sketch
        if node is None or node not in sketch.nodes:
            return CommandResult.failure("Select a point on the curve to split at.")
        targets = [curve.id for curve in sketch.curves if node in curve.nodes and (curve_id is None or curve.id == curve_id)]
        if not targets:
            return CommandResult.failure("That point is not on a curve.")

        def change(sketch: Any, projector: MeshProjector) -> str:
            made = []
            for target in targets:
                curve = sketch.curve(target)
                if curve is not None and (curve.closed or node not in (curve.nodes[0], curve.nodes[-1])):
                    made.extend(sketch.split_curve(target, node, projector))
            if not made:
                raise ValueError("That point is already the end of the curve.")
            self.state.model.selected_curve_ids = list(dict.fromkeys(made))
            return f"Split at the point: {len(set(made))} curve(s)"

        return self._sketch_edit("Split Sketch Curve", change)

    def _curves_to_edit(self, curve_ids: tuple[str, ...] | None) -> list[str]:
        if curve_ids:
            return list(curve_ids)
        model = self.state.model
        if model.selected_curve_ids:
            return list(model.selected_curve_ids)
        session = self.session
        if session is not None and session.selected_node is not None:
            return [curve.id for curve in model.sketch.curves if session.selected_node in curve.nodes]
        return []

    def sketch_toggle_closed(self, curve_ids: tuple[str, ...] | None = None) -> CommandResult:
        ids = self._curves_to_edit(curve_ids)
        if not ids:
            return CommandResult.failure("Select a curve first (click it).")

        def change(sketch: Any, projector: MeshProjector) -> str:
            for value in ids:
                curve = sketch.curve(value)
                if curve is not None:
                    sketch.set_closed(value, not curve.closed, projector)
            states = {sketch.curve(value).closed for value in ids if sketch.curve(value) is not None}
            return "Curve closed" if states == {True} else ("Curve opened" if states == {False} else "Curves opened / closed")

        return self._sketch_edit("Open / Close Sketch Curve", change)

    def sketch_reverse(self, curve_ids: tuple[str, ...] | None = None) -> CommandResult:
        ids = self._curves_to_edit(curve_ids)
        if not ids:
            return CommandResult.failure("Select a curve first (click it).")

        def change(sketch: Any, projector: MeshProjector) -> str:
            for value in ids:
                sketch.reverse(value)
            return f"Reversed {len(ids)} curve(s)"

        return self._sketch_edit("Reverse Sketch Curve", change)

    def sketch_options(self, *, smoothness: float | None = None, feature: bool | None = None) -> CommandResult:
        """Smoothness / crease following: for the selected curves (rebuilt, one undo step) and
        for the curves drawn from now on."""

        session = self._session_for("sketch")
        if isinstance(session, CommandResult):
            return session
        if smoothness is not None:
            session.sketch_smoothness = float(np.clip(smoothness, 0.0, 1.0))
        if feature is not None:
            session.sketch_feature = bool(feature)
        self._placed_line = None
        if session.sketch_points:
            session.sketch_line = self._sketch_preview_line(session)
        ids = list(self.state.model.selected_curve_ids)
        if not ids:
            how = "follow body lines" if session.sketch_feature else "run along the surface"
            return CommandResult.ok(status=f"New curves {how}, smoothness {session.sketch_smoothness:.2f}", changed=True)

        def change(sketch: Any, projector: MeshProjector) -> str:
            for value in ids:
                sketch.set_options(value, projector, smoothness=smoothness, feature=feature)
            return f"Updated {len(ids)} curve(s)"

        return self._sketch_edit("Sketch Curve Options", change)

    def sketch_crease_strength(self) -> np.ndarray | None:
        """Per display-mesh vertex, the scan's crease strength (0 to 1), for "Show body lines"."""

        mesh_object = self.state.mesh_object
        projector = self.sketch_projector()
        if mesh_object is None or projector is None:
            return None
        display = mesh_object.display_mesh
        key = (id(display.vertices), id(projector))
        cached = self._crease_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        graph = projector.graph
        local = np.asarray(display.vertices, dtype=float)
        world = _apply(self.transform.current_object_matrix(), local)
        _distance, nearest = graph.tree.query(world)
        strength = graph.crease[nearest]
        self._crease_cache = (key, strength)
        return strength

    def sketch_select_curves(self, curve_ids: tuple[str, ...], *, add: bool = False) -> CommandResult:
        sketch = self.state.model.sketch
        valid = [value for value in curve_ids if sketch.curve(value) is not None]
        if not add:
            self.state.model.selected_feature = ""
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
        return self.loft(curve_ids)

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


def _kernel_failure(prefix: str, reply: KernelReply) -> CommandResult:
    message = f"{prefix}: {reply.error}"
    return CommandResult.failure(message, status=message)


__all__ = (
    "EXTRUDE_MODES",
    "FitOptions",
    "ModelingController",
    "SECTION_PLANES",
    "SELECTION_MODES",
    "TOOLS",
    "TOOL_TITLES",
    "ToolSession",
)
