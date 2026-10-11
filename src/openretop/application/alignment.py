"""Align to World (H-01), the application side: move the scan and everything built on it
by one rigid motion, and put it all back for undo.

The scan moves through its pose (location / rotation, so a saved project reopens aligned);
everything made on it is stored in world coordinates and is moved itself: model surfaces and
bodies (BREPs moved by the kernel, display meshes and edges here), sketch frames and the
history's inputs, Surface Sketch points and curves, section cuts with their planes, and
measurements. Regions and Fit Surface selections are triangle indices of the scan and follow
it as they are.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Sequence

import numpy as np

from openretop.application.section_controller import (
    SectionWorkflowSnapshot,
    capture_section_workflow_state,
    restore_section_workflow_state,
    sync_display_section_result,
)
from openretop.application.state import AppState, Measurement
from openretop.geometry.sections import SectionPolyline
from openretop.modeling.alignment import apply_directions, apply_points, moved_frame, world_plane_of
from openretop.modeling.document import ModelDocument
from openretop.sections.section_state import plane_normal, plane_origin, set_plane_origin_normal


@dataclass
class AlignSnapshot:
    pose: Any  # ObjectTransformSnapshot
    model: tuple[Any, ...]
    sections: SectionWorkflowSnapshot
    measurements: tuple[Measurement, ...]


def capture_alignment_state(state: AppState, transform: Any) -> AlignSnapshot:
    return AlignSnapshot(
        pose=transform.capture_object(),
        model=state.model.snapshot(),
        sections=capture_section_workflow_state(state),
        measurements=tuple(state.measure.measurements),
    )


def restore_alignment_state(state: AppState, transform: Any, snapshot: AlignSnapshot) -> None:
    transform.restore_object(snapshot.pose)
    state.model.restore(snapshot.model)  # type: ignore[arg-type]
    restore_section_workflow_state(state, snapshot.sections)
    state.measure.measurements = list(snapshot.measurements)
    sync_display_section_result(state)


def breps_to_move(model: ModelDocument) -> list[bytes]:
    """Every BREP stored in world coordinates: the entities', then the history's base features'."""

    breps = [entity.brep for entity in model.entities]
    breps += [feature.inputs["brep"] for feature in model.timeline.features if feature.kind == "base" and "brep" in feature.inputs]
    return breps


def _moved_sketch_params(params: dict[str, Any], matrix: np.ndarray) -> dict[str, Any]:
    """A sketch's inputs with its frame moved; its world plane and offset follow when the
    moved frame is still a world plane (an Align that only shifts), else the frame rules."""

    if "frame" not in params:
        return params
    moved = dict(params)
    moved["frame"] = moved_frame(params["frame"], matrix)
    plane = world_plane_of(moved["frame"], 1e-7)
    if plane is not None:
        moved["plane"], moved["offset"] = plane[0], plane[1]
    return moved


def move_built_geometry(state: AppState, matrix: np.ndarray, moved_breps: Sequence[bytes]) -> dict[str, int]:
    """Move everything made on the scan by ``matrix`` (``moved_breps``: ``breps_to_move``'s
    BREPs, moved by the kernel). Returns what moved, for the status line."""

    model = state.model
    counts = {"surfaces": 0, "bodies": 0, "curves": 0, "sections": 0, "measurements": 0, "sketches": 0}
    moved = list(moved_breps)
    entity_breps, base_breps = moved[: len(model.entities)], moved[len(model.entities) :]
    entities = []
    for entity, brep in zip(model.entities, entity_breps, strict=True):
        params = _moved_sketch_params(entity.params, matrix) if entity.kind == "profile" else entity.params
        entities.append(
            replace(
                entity,
                brep=brep,
                vertices=apply_points(matrix, entity.vertices),
                edges=[apply_points(matrix, edge) for edge in entity.edges],
                params=params,
            )
        )
        if entity.kind == "profile":
            counts["sketches"] += 1
        elif entity.is_body:
            counts["bodies"] += 1
        else:
            counts["surfaces"] += 1
    model.entities = entities
    base = iter(base_breps)
    for feature in model.timeline.features:
        if feature.kind == "base" and "brep" in feature.inputs:
            feature.inputs = {**feature.inputs, "brep": next(base)}
        elif feature.kind == "sketch":
            feature.inputs = _moved_sketch_params(feature.inputs, matrix)
        feature.result = None  # replayed from the moved inputs on the next edit
    sketch = model.sketch
    sketch.nodes = {key: apply_points(matrix, value) for key, value in sketch.nodes.items()}
    for curve in sketch.curves:
        curve.polyline = apply_points(matrix, curve.polyline)
        counts["curves"] += 1
    collection = state.section_collection
    moved_planes = set()
    for stored in collection.results:
        result = stored.result
        origin = None if stored.plane_origin is None else apply_points(matrix, stored.plane_origin)
        normal = None if stored.plane_normal is None else apply_directions(matrix, stored.plane_normal)
        stored.result = replace(
            result,
            polylines=tuple(SectionPolyline(apply_points(matrix, polyline.points)) for polyline in result.polylines),
            plane_origin=None if result.plane_origin is None else apply_points(matrix, result.plane_origin),
            plane_normal=None if result.plane_normal is None else apply_directions(matrix, result.plane_normal),
            is_arbitrary_plane=True,
        )
        stored.plane_origin, stored.plane_normal, stored.is_arbitrary_plane = origin, normal, True
        moved_planes.add(stored.plane_id)
        counts["sections"] += 1
    for plane in collection.planes:
        if plane.id in moved_planes:  # a plane with cuts moves with them; an empty one stays a world plane
            set_plane_origin_normal(plane, apply_points(matrix, plane_origin(plane)), apply_directions(matrix, plane_normal(plane)))
    measure = state.measure
    measure.measurements = [
        replace(item, start=tuple(apply_points(matrix, item.start).tolist()), end=tuple(apply_points(matrix, item.end).tolist()))
        for item in measure.measurements
    ]
    if measure.pending is not None:
        measure.pending = tuple(apply_points(matrix, measure.pending).tolist())  # type: ignore[assignment]
    counts["measurements"] = len(measure.measurements)
    sync_display_section_result(state)
    model.revision += 1
    return counts


def moved_text(counts: dict[str, int]) -> str:
    """'3 surfaces, 1 body and 6 curves' (empty when nothing else moves)."""

    names = {"surfaces": ("surface", "surfaces"), "bodies": ("body", "bodies"), "sketches": ("sketch", "sketches"),
             "curves": ("curve", "curves"), "sections": ("section cut", "section cuts"), "measurements": ("measurement", "measurements")}
    parts = [f"{count} {names[key][count != 1]}" for key, count in counts.items() if count]
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


__all__ = (
    "AlignSnapshot",
    "breps_to_move",
    "capture_alignment_state",
    "move_built_geometry",
    "moved_text",
    "restore_alignment_state",
)
