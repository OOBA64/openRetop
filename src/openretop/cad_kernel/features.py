"""Solid features from sketch profiles (S-14): extrude, with depth per loop and draft.

A profile's closed loops are faces on the sketch plane. Outer loops (not inside another) are
extruded over their depth range and united; loops inside them (holes) are extruded over their
own range and cut, so a pocket that stops at a floor stays a pocket instead of a through hole.
Depths run along the plane's normal: ``(low, high)`` with ``low <= high``, the sketch plane at
0. Draft tapers the walls away from the sketch plane on both sides (the plane is the parting
line); a hole tapers the other way, so a pocket narrows as it deepens.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from openretop.cad_kernel.profiles import PlaneFrame, loop_faces

EXTRUDE_MODES = ("new", "add", "cut")


def prism(face: Any, normal: np.ndarray, low: float, high: float, draft: float = 0.0) -> Any:
    """The face swept from ``low`` to ``high`` along ``normal`` (draft in degrees)."""

    import cadquery as cq

    if high - low <= 1e-9:
        raise ValueError("the extrusion has no depth")
    base = cq.Face(face)
    n = cq.Vector(*normal.tolist())
    if abs(draft) < 1e-9 or low >= 0.0 or high <= 0.0:
        start = low if (abs(draft) < 1e-9 or low >= 0.0) else high
        moved = base.translate(n * start) if abs(start) > 0.0 else base
        direction = n * (high - low) if start == low else n * (low - high)
        return cq.Solid.extrudeLinear(moved, direction, taper=draft).wrapped
    # both sides of the parting plane: each side tapers away from it
    upper = cq.Solid.extrudeLinear(base, n * high, taper=draft)
    lower = cq.Solid.extrudeLinear(base, n * low, taper=draft)
    return _clean(upper.fuse(lower).wrapped)


def extrude(
    frame: PlaneFrame,
    loops: list[dict[str, Any]],
    ranges: list[tuple[float, float]],
    *,
    draft: float = 0.0,
) -> Any:
    """One solid from a profile: outer loops added over their ranges, holes cut over theirs."""

    import cadquery as cq

    if len(ranges) != len(loops):
        raise ValueError("one depth range per loop is needed")
    faces = loop_faces(frame, loops)
    if not faces:
        raise ValueError("the sketch has no closed loop to extrude")
    normal = frame.normal
    body = None
    for face, index, depth in faces:
        if depth % 2:
            continue
        low, high = ranges[index]
        piece = cq.Shape.cast(prism(face, normal, low, high, draft))
        body = piece if body is None else body.fuse(piece)
    if body is None:
        raise ValueError("the sketch has only holes")
    outer = [ranges[index] for _face, index, depth in faces if depth % 2 == 0]
    bottom, top = min(low for low, _high in outer), max(high for _low, high in outer)
    # a hole reaching the body's end goes through it: a cut ending on (or a hair short of) a
    # face leaves a skin over the hole, so it runs a little past instead
    hair = 2e-4 * max(top - bottom, 1e-9) + 1e-6
    past = 0.01 * (top - bottom) + 10.0 * hair
    for face, index, depth in faces:
        if depth % 2 == 0:
            continue
        low, high = ranges[index]
        low = bottom - past if low <= bottom + hair else low
        high = top + past if high >= top - hair else high
        body = body.cut(cq.Shape.cast(prism(face, normal, low, high, -draft)))
    return _clean(body.wrapped)


def combine(body: Any, target: Any | None, mode: str) -> Any:
    """``new``: the body; ``add``: united with the target; ``cut``: taken out of it."""

    import cadquery as cq

    if mode not in EXTRUDE_MODES:
        raise ValueError(f"unknown extrude mode: {mode}")
    if mode == "new":
        return body
    if target is None:
        raise ValueError("add and cut need a body to work on")
    first, second = cq.Shape.cast(target), cq.Shape.cast(body)
    result = first.fuse(second) if mode == "add" else first.cut(second)
    return _clean(result.wrapped)


def _clean(shape: Any) -> Any:
    """Merge the coplanar faces and collinear edges booleans leave behind."""

    from OCP.ShapeUpgrade import ShapeUpgrade_UnifySameDomain

    unify = ShapeUpgrade_UnifySameDomain(shape, True, True, True)
    unify.Build()
    return unify.Shape()


def is_valid(shape: Any) -> bool:
    from OCP.BRepCheck import BRepCheck_Analyzer

    return bool(BRepCheck_Analyzer(shape).IsValid())


__all__ = ("EXTRUDE_MODES", "combine", "extrude", "is_valid", "prism")
