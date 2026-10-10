"""Render items for the model and the surfacing tools (selection, previews, trim pieces,
deviation map), from plain inputs: the viewer does not depend on the application layer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

import numpy as np

from openretop.viewer.scene_types import (
    DisplayStyleSnapshot,
    ModelEdgesRenderItem,
    ModelFaceRenderItem,
    ScanOverlayRenderItem,
)

SELECTION_COLOR = (0.98, 0.55, 0.20)  # the area picked for Fit Surface: warm, unlike any surface
PREVIEW_COLOR = (0.55, 0.85, 1.00)
DROPPED_PIECE_COLOR = (0.55, 0.57, 0.62)
EDGE_COLOR = (0.10, 0.11, 0.13)
SELECTED_EDGE_COLOR = (1.00, 0.85, 0.25)
CHAIN_EDGE_COLOR = (0.95, 0.30, 0.85)
SKETCH_CURVE_COLOR = (0.85, 0.40, 0.98)  # Surface Sketch curves: violet, unlike surfaces and the selection
SELECTED_SKETCH_COLOR = (1.00, 0.85, 0.25)
SECTION_COLOR = (0.98, 0.55, 0.20)  # the scan's section on the sketch plane
PLANE_COLOR = (0.55, 0.70, 0.95)

# deviation colour scale (signed distance / tolerance)
_IN_TOLERANCE = np.array([0.30, 0.78, 0.40])
_ABOVE = np.array([[0.96, 0.88, 0.25], [0.93, 0.25, 0.20]])  # just above -> far above
_BELOW = np.array([[0.30, 0.80, 0.95], [0.20, 0.30, 0.92]])  # just below -> far below
_UNKNOWN = np.array([0.55, 0.56, 0.58])
DEVIATION_RANGE = 4.0  # colours saturate at this many tolerances


def model_node_id(entity_id: str) -> str:
    return f"model:{entity_id}"


def model_id_from_node(node_id: str) -> str | None:
    return node_id[len("model:"):] if str(node_id).startswith("model:") else None


def deviation_colors(distances: object, tolerance: float) -> np.ndarray:
    """RGB bytes per point: green within +/- tolerance, yellow to red above, cyan to blue below."""

    values = np.asarray(distances, dtype=float).ravel()
    band = max(float(tolerance), 1e-12)
    ratio = values / band
    colors = np.tile(_IN_TOLERANCE, (len(values), 1))
    known = np.isfinite(values)
    for sign, ramp in ((1.0, _ABOVE), (-1.0, _BELOW)):
        outside = known & (sign * ratio > 1.0)
        t = np.clip((sign * ratio[outside] - 1.0) / (DEVIATION_RANGE - 1.0), 0.0, 1.0)[:, None]
        colors[outside] = ramp[0] * (1.0 - t) + ramp[1] * t
    colors[~known] = _UNKNOWN
    return np.round(colors * 255.0).astype(np.uint8)


@dataclass(frozen=True)
class ModelingSceneInput:
    entities: Sequence[Any] = ()  # ModelEntity-like: id, vertices, triangles, edges, color, visible, is_body
    selected_ids: frozenset[str] = frozenset()
    selection_mask: np.ndarray | None = field(default=None, compare=False)
    selection_revision: int = 0
    preview: dict[str, Any] | None = field(default=None, compare=False)
    trim_pieces: Sequence[dict[str, Any]] | None = field(default=None, compare=False)
    deviation: np.ndarray | None = field(default=None, compare=False)  # signed, per display vertex
    deviation_tolerance: float = 0.05
    chain_edges: Sequence[tuple[str, int]] = ()  # (entity id, edge) picked for a fill boundary
    sketch_curves: Sequence[tuple[str, np.ndarray, bool]] = ()  # (curve id, polyline, selected)
    # Section Sketch: the scan's section, the fitted profile and the plane's outline (world)
    section_lines: Sequence[np.ndarray] = field(default=(), compare=False)
    profile_lines: Sequence[np.ndarray] = field(default=(), compare=False)
    section_plane: np.ndarray | None = field(default=None, compare=False)
    creases: np.ndarray | None = field(default=None, compare=False)
    profile_highlight: np.ndarray | None = field(default=None, compare=False)  # the picked segment  # per display vertex, 0..1: "Show body lines"


def modeling_items(
    modeling: ModelingSceneInput,
    mesh_object: object | None,
) -> tuple[tuple[ModelFaceRenderItem, ...], tuple[ModelEdgesRenderItem, ...], tuple[ScanOverlayRenderItem, ...]]:
    faces: list[ModelFaceRenderItem] = []
    edges: list[ModelEdgesRenderItem] = []
    overlays: list[ScanOverlayRenderItem] = []
    trimming = modeling.trim_pieces is not None
    chain = {(str(entity), int(edge)) for entity, edge in modeling.chain_edges}
    for entity in modeling.entities:
        visible = bool(entity.visible) and not trimming  # while trimming the pieces stand in
        # with a deviation map up, the surfaces step aside (edges only) so the coloured scan shows
        faces_visible = visible and modeling.deviation is None
        selected = entity.id in modeling.selected_ids
        token = hash((entity.id, id(entity.vertices)))
        node = model_node_id(entity.id)
        sketch = getattr(entity, "kind", "") == "profile"  # a sketch: its lines matter, its face is a hint
        faces.append(
            ModelFaceRenderItem(
                id=f"model-face:{entity.id}",
                revision=token,
                vertices=entity.vertices,
                triangles=entity.triangles,
                visible=faces_visible,
                selected=selected,
                role="body" if entity.is_body else "surface",
                style=DisplayStyleSnapshot(
                    color=_brighter(entity.color) if selected else tuple(entity.color), opacity=0.35 if sketch else 1.0
                ),
                selection_keys=(node,),
            )
        )
        if entity.edges:
            highlighted = [index for index in range(len(entity.edges)) if (entity.id, index) in chain]
            edges.append(
                ModelEdgesRenderItem(
                    id=f"model-edges:{entity.id}",
                    revision=token,
                    polylines=tuple(entity.edges),
                    visible=visible,
                    style=DisplayStyleSnapshot(
                        color=SELECTED_EDGE_COLOR if selected else (SKETCH_CURVE_COLOR if sketch else EDGE_COLOR),
                        line_width=(3.0 if sketch else 2.0) if selected else (2.5 if sketch else 1.2),
                    ),
                    selection_keys=(node,),
                )
            )
            if highlighted and visible:
                edges.append(
                    ModelEdgesRenderItem(
                        id=f"model-chain:{entity.id}",
                        revision=hash((token, tuple(highlighted))),
                        polylines=tuple(entity.edges[index] for index in highlighted),
                        style=DisplayStyleSnapshot(color=CHAIN_EDGE_COLOR, line_width=4.0),
                    )
                )
    for curve_id, polyline, selected in modeling.sketch_curves:
        edges.append(
            ModelEdgesRenderItem(
                id=f"sketch-curve:{curve_id}",
                revision=hash(("sketch", curve_id, id(polyline), len(polyline))),
                polylines=(polyline,),
                style=DisplayStyleSnapshot(
                    color=SELECTED_SKETCH_COLOR if selected else SKETCH_CURVE_COLOR, line_width=3.5 if selected else 2.5
                ),
                selection_keys=(f"sketch:{curve_id}",),
            )
        )
    for name, lines, color, width in (
        ("section-plane", () if modeling.section_plane is None else (modeling.section_plane,), PLANE_COLOR, 1.0),
        ("section-scan", modeling.section_lines, SECTION_COLOR, 1.5),
        ("section-profile", modeling.profile_lines, SKETCH_CURVE_COLOR, 3.0),
        ("section-picked", () if modeling.profile_highlight is None else (modeling.profile_highlight,), SELECTED_SKETCH_COLOR, 5.0),
    ):
        if len(lines):
            edges.append(
                ModelEdgesRenderItem(
                    id=name,
                    revision=hash((name, tuple(id(line) for line in lines))),
                    polylines=tuple(lines),
                    style=DisplayStyleSnapshot(color=color, line_width=width),
                )
            )
    preview = modeling.preview
    if preview is not None:
        faces.append(
            ModelFaceRenderItem(
                id="model-preview",
                revision=hash(("preview", id(preview["vertices"]))),
                vertices=preview["vertices"],
                triangles=preview["triangles"],
                role="preview",
                style=DisplayStyleSnapshot(color=PREVIEW_COLOR, opacity=0.8),
            )
        )
        edges.append(
            ModelEdgesRenderItem(
                id="model-preview-edges",
                revision=hash(("preview-edges", id(preview["vertices"]))),
                polylines=tuple(preview.get("edges", ())),
                style=DisplayStyleSnapshot(color=EDGE_COLOR, line_width=1.5),
            )
        )
    for index, piece in enumerate(modeling.trim_pieces or ()):
        keep = bool(piece["keep"])
        source = next((entity for entity in modeling.entities if entity.id == piece.get("source_id")), None)
        color = tuple(source.color) if (keep and source is not None) else DROPPED_PIECE_COLOR
        faces.append(
            ModelFaceRenderItem(
                id=f"trim-piece:{index}",
                revision=hash(("piece", index, id(piece["vertices"]))),
                vertices=piece["vertices"],
                triangles=piece["triangles"],
                role="piece_keep" if keep else "piece_drop",
                style=DisplayStyleSnapshot(color=color, opacity=1.0 if keep else 0.28),
            )
        )
        edges.append(
            ModelEdgesRenderItem(
                id=f"trim-piece-edges:{index}",
                revision=hash(("piece-edges", index, id(piece["vertices"]))),
                polylines=tuple(piece.get("edges", ())),
                style=DisplayStyleSnapshot(color=EDGE_COLOR, line_width=1.0, opacity=1.0 if keep else 0.35),
            )
        )
    mesh = None if mesh_object is None else getattr(mesh_object, "display_mesh", None)
    if mesh is not None:
        transform = np.asarray(getattr(mesh_object, "transform_matrix", np.identity(4)), dtype=float).reshape(4, 4)
        mask = modeling.selection_mask
        if mask is not None and np.any(mask):
            overlays.append(
                ScanOverlayRenderItem(
                    id="scan-selection",
                    revision=hash(("selection", modeling.selection_revision, id(mesh.triangles))),
                    vertices=mesh.vertices,
                    triangles=mesh.triangles,
                    triangle_mask=mask,
                    transform=transform,
                    style=DisplayStyleSnapshot(color=SELECTION_COLOR, opacity=0.85),
                )
            )
        if modeling.creases is not None and len(modeling.creases) == len(mesh.vertices):
            overlays.append(
                ScanOverlayRenderItem(
                    id="scan-creases",
                    revision=hash(("creases", id(modeling.creases))),
                    vertices=mesh.vertices,
                    triangles=mesh.triangles,
                    vertex_colors=crease_colors(modeling.creases),
                    transform=transform,
                )
            )
        if modeling.deviation is not None and len(modeling.deviation) == len(mesh.vertices):
            overlays.append(
                ScanOverlayRenderItem(
                    id="scan-deviation",
                    revision=hash(("deviation", id(modeling.deviation), modeling.deviation_tolerance)),
                    vertices=mesh.vertices,
                    triangles=mesh.triangles,
                    vertex_colors=deviation_colors(modeling.deviation, modeling.deviation_tolerance),
                    transform=transform,
                )
            )
    return tuple(faces), tuple(edges), tuple(overlays)


def crease_colors(strength: object) -> np.ndarray:
    """RGB bytes: the scan's grey, turning red along its creases (body lines)."""

    values = np.clip(np.asarray(strength, dtype=float).ravel(), 0.0, 1.0)[:, None]
    base, line = np.array([0.72, 0.74, 0.78]), np.array([0.98, 0.22, 0.16])
    return np.round((base * (1.0 - values) + line * values) * 255.0).astype(np.uint8)


def _brighter(color: Sequence[float]) -> tuple[float, float, float]:
    r, g, b = (float(value) for value in color)
    return (min(1.0, r * 0.6 + 0.4), min(1.0, g * 0.6 + 0.4), min(1.0, b * 0.6 + 0.4))


__all__ = (
    "ModelingSceneInput",
    "crease_colors",
    "deviation_colors",
    "model_id_from_node",
    "model_node_id",
    "modeling_items",
)
