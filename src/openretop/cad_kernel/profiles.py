"""Sketch profiles as exact geometry: lines and arcs on a plane, as wires and planar faces.

A profile arrives as plain data (from ``modeling.profile2d``): a plane frame and, per loop,
its segments in the plane's 2D coordinates. Each segment becomes an exact OCC edge (a line,
an arc through its start, middle and end, or a full circle), consecutive edges share their
vertices, and closed loops become planar faces, a loop inside another a hole in it (an island
inside a hole a face again). Open loops stay wires.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PlaneFrame:
    origin: np.ndarray
    u: np.ndarray
    v: np.ndarray

    @property
    def normal(self) -> np.ndarray:
        normal = np.cross(self.u, self.v)
        return normal / max(float(np.linalg.norm(normal)), 1e-15)

    def to_world(self, points: object) -> np.ndarray:
        values = np.asarray(points, dtype=float).reshape(-1, 2)
        return self.origin + values[:, :1] * self.u + values[:, 1:2] * self.v

    def to_plane(self, points: object) -> np.ndarray:
        values = np.asarray(points, dtype=float).reshape(-1, 3) - self.origin
        return np.c_[values @ self.u, values @ self.v]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlaneFrame:
        u = np.asarray(data["u"], dtype=float)
        v = np.asarray(data["v"], dtype=float)
        return cls(np.asarray(data["origin"], dtype=float), u / np.linalg.norm(u), v / np.linalg.norm(v))

    def to_dict(self) -> dict[str, list[float]]:
        return {"origin": self.origin.tolist(), "u": self.u.tolist(), "v": self.v.tolist()}


def loop_edges(frame: PlaneFrame, segments: list[dict[str, Any]]) -> list[Any]:
    """Exact edges of one loop, consecutive edges sharing their vertices."""

    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge, BRepBuilderAPI_MakeVertex
    from OCP.GC import GC_MakeArcOfCircle
    from OCP.gp import gp_Ax2, gp_Circ, gp_Dir, gp_Pnt

    def point(xy: object) -> Any:
        return gp_Pnt(*frame.to_world(xy)[0].tolist())

    if not segments:
        return []
    starts = [np.asarray(segment["start"], dtype=float) for segment in segments]
    vertices = [BRepBuilderAPI_MakeVertex(point(start)).Vertex() for start in starts]
    edges = []
    count = len(segments)
    for index, segment in enumerate(segments):
        start, end = np.asarray(segment["start"], dtype=float), np.asarray(segment["end"], dtype=float)
        first = vertices[index]
        closing = index == count - 1 and float(np.linalg.norm(end - starts[0])) <= 1e-9 * max(1.0, float(np.abs(end).max()))
        if closing:
            last = vertices[0]
        elif index + 1 < count:
            last = vertices[index + 1]
        else:
            last = BRepBuilderAPI_MakeVertex(point(end)).Vertex()
        if segment["kind"] == "line":
            maker = BRepBuilderAPI_MakeEdge(first, last)
        elif count == 1 and closing:  # a full circle
            center = frame.to_world(segment["center"])[0]
            axis = gp_Ax2(gp_Pnt(*center.tolist()), gp_Dir(*(frame.normal if segment.get("ccw", True) else -frame.normal).tolist()))
            circle = gp_Circ(axis, float(segment["radius"]))
            maker = BRepBuilderAPI_MakeEdge(circle, first, first)
        else:
            middle = _arc_middle(segment)
            arc = GC_MakeArcOfCircle(point(start), point(middle), point(end)).Value()
            maker = BRepBuilderAPI_MakeEdge(arc, first, last)
        if not maker.IsDone():
            raise ValueError(f"segment {index + 1} ({segment['kind']}) could not be made")
        edges.append(maker.Edge())
    return edges


def _arc_middle(segment: dict[str, Any]) -> np.ndarray:
    center = np.asarray(segment["center"], dtype=float)
    start = np.asarray(segment["start"], dtype=float) - center
    end = np.asarray(segment["end"], dtype=float) - center
    a0, a1 = math.atan2(start[1], start[0]), math.atan2(end[1], end[0])
    sweep = (a1 - a0) % (2 * math.pi)
    if not segment.get("ccw", True):
        sweep -= 2 * math.pi
    angle = a0 + sweep / 2.0
    return center + float(segment["radius"]) * np.array([math.cos(angle), math.sin(angle)])


def profile_shape(frame: PlaneFrame, loops: list[dict[str, Any]]) -> tuple[Any, dict[str, int]]:
    """Faces for the closed loops (holes where nested), wires for the open ones.

    ``loops``: ``{"segments": [...], "closed": bool, "outline": (n, 2) samples}``; the outline
    (any polyline along the loop) decides which loop lies inside which.
    """

    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt
    from OCP.ShapeFix import ShapeFix_Face

    from openretop.cad_kernel.surfacing import compound

    wires: list[Any] = []
    closed: list[bool] = []
    outlines: list[np.ndarray] = []
    for number, loop in enumerate(loops, start=1):
        maker = BRepBuilderAPI_MakeWire()
        for edge in loop_edges(frame, loop["segments"]):
            maker.Add(edge)
        if not maker.IsDone():
            raise ValueError(f"loop {number}: its segments do not join into one wire")
        wires.append(maker.Wire())
        closed.append(bool(loop.get("closed", False)) and maker.Wire().Closed())
        outlines.append(np.asarray(loop.get("outline", np.zeros((0, 2))), dtype=float).reshape(-1, 2))
    plane = gp_Pln(gp_Ax3(gp_Pnt(*frame.origin.tolist()), gp_Dir(*frame.normal.tolist()), gp_Dir(*frame.u.tolist())))
    shapes: list[Any] = []
    loop_indices = [index for index, is_closed in enumerate(closed) if is_closed]
    depth = {index: sum(_inside(outlines[index], outlines[other]) for other in loop_indices if other != index) for index in loop_indices}
    faces = 0
    for index in loop_indices:
        if depth[index] % 2:
            continue  # a hole, added to the face around it
        face_maker = BRepBuilderAPI_MakeFace(plane, wires[index])
        for hole in loop_indices:
            if depth[hole] == depth[index] + 1 and _inside(outlines[hole], outlines[index]):
                face_maker.Add(wires[hole])
        if not face_maker.IsDone():
            raise ValueError("a closed loop could not be made into a face")
        fixer = ShapeFix_Face(face_maker.Face())
        fixer.FixOrientation()
        fixer.Perform()
        shapes.append(fixer.Face())
        faces += 1
    shapes.extend(wire for wire, is_closed in zip(wires, closed, strict=True) if not is_closed)
    if not shapes:
        raise ValueError("the profile is empty")
    shape = shapes[0] if len(shapes) == 1 else compound(shapes)
    return shape, {"faces": faces, "wires": sum(1 for value in closed if not value), "loops": len(loops)}


def loop_faces(frame: PlaneFrame, loops: list[dict[str, Any]]) -> list[tuple[Any, int, int]]:
    """Each closed loop as its own planar face (no holes), with its index and nesting
    depth: 0 outermost, 1 a hole in it, 2 an island in the hole ..."""

    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace, BRepBuilderAPI_MakeWire
    from OCP.gp import gp_Ax3, gp_Dir, gp_Pln, gp_Pnt
    from OCP.ShapeFix import ShapeFix_Face

    plane = gp_Pln(gp_Ax3(gp_Pnt(*frame.origin.tolist()), gp_Dir(*frame.normal.tolist()), gp_Dir(*frame.u.tolist())))
    outlines = [np.asarray(loop.get("outline", np.zeros((0, 2))), dtype=float).reshape(-1, 2) for loop in loops]
    closed = [index for index, loop in enumerate(loops) if loop.get("closed", False)]
    faces = []
    for index in closed:
        maker = BRepBuilderAPI_MakeWire()
        for edge in loop_edges(frame, loops[index]["segments"]):
            maker.Add(edge)
        if not maker.IsDone() or not maker.Wire().Closed():
            continue
        face_maker = BRepBuilderAPI_MakeFace(plane, maker.Wire())
        if not face_maker.IsDone():
            raise ValueError(f"loop {index + 1} could not be made into a face")
        fixer = ShapeFix_Face(face_maker.Face())
        fixer.FixOrientation()
        fixer.Perform()
        depth = sum(_inside(outlines[index], outlines[other]) for other in closed if other != index)
        faces.append((fixer.Face(), index, depth))
    return faces


def _inside(inner: np.ndarray, outer: np.ndarray) -> bool:
    """Whether loop ``inner`` lies inside loop ``outer`` (both as 2D outlines)."""

    if len(inner) == 0 or len(outer) < 3:
        return False
    x, y = inner[len(inner) // 2]
    ax, ay = outer[:, 0], outer[:, 1]
    bx, by = np.roll(ax, -1), np.roll(ay, -1)
    crossing = (ay > y) != (by > y)
    with np.errstate(divide="ignore", invalid="ignore"):
        at = ax + (y - ay) * (bx - ax) / (by - ay)
    return bool(np.count_nonzero(crossing & (x < at)) % 2)


__all__ = ("PlaneFrame", "loop_edges", "loop_faces", "profile_shape")
