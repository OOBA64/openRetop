"""The model being built from the scan: surfaces and bodies made by the surfacing tools (S-04).

Each entity keeps its BREP (the exact geometry, from the kernel worker), what is needed to show
it without OpenCASCADE (a display mesh and edge polylines), how it was made (the tool and its
parameters) and its fit statistics. Entities are replaced, never edited in place, so an undo
snapshot is a shallow copy of the list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from openretop.modeling.sketch import Sketch

# distinct, mid-saturation colours that read on the grey scan and on each other
PALETTE: tuple[tuple[float, float, float], ...] = (
    (0.36, 0.62, 0.95),
    (0.95, 0.62, 0.30),
    (0.45, 0.80, 0.50),
    (0.86, 0.45, 0.72),
    (0.95, 0.85, 0.35),
    (0.40, 0.80, 0.85),
    (0.70, 0.55, 0.95),
    (0.92, 0.45, 0.45),
)

SOLID_COLOR = (0.62, 0.70, 0.80)

KIND_LABELS = {
    "freeform": "Freeform",
    "plane": "Plane",
    "cylinder": "Cylinder",
    "cone": "Cone",
    "sphere": "Sphere",
    "torus": "Torus",
    "loft": "Loft",
    "fill": "Fill",
    "extend": "Extended",
    "piece": "Trimmed",
    "patch": "Patch",
    "profile": "Sketch",
    "shell": "Shell",
    "solid": "Solid",
}


@dataclass
class ModelEntity:
    id: str
    name: str
    kind: str  # freeform, plane, ..., loft, fill, extend, piece, shell, solid
    tool: str  # the tool that made it: fit_surface, loft, fill, extend, trim, sew
    brep: bytes
    vertices: np.ndarray
    triangles: np.ndarray
    edges: list[np.ndarray] = field(default_factory=list)
    color: tuple[float, float, float] = PALETTE[0]
    visible: bool = True
    params: dict[str, Any] = field(default_factory=dict)  # the tool's inputs, to edit and rebuild
    stats: dict[str, Any] = field(default_factory=dict)  # rms, max_error, area, volume, ...
    sources: tuple[str, ...] = ()  # entities it was made from

    @property
    def is_body(self) -> bool:
        return self.kind in ("shell", "solid")

    @property
    def label(self) -> str:
        return KIND_LABELS.get(self.kind, self.kind.title())


@dataclass
class ModelDocument:
    entities: list[ModelEntity] = field(default_factory=list)
    selected_ids: list[str] = field(default_factory=list)
    counter: int = 0
    revision: int = 0
    # the 3D Sketch: points on the scan and the curves through them
    sketch: Sketch = field(default_factory=Sketch)
    selected_curve_ids: list[str] = field(default_factory=list)

    def get(self, entity_id: str) -> ModelEntity | None:
        return next((entity for entity in self.entities if entity.id == entity_id), None)

    def new_id(self) -> str:
        self.counter += 1
        return f"model-{self.counter}"

    def next_name(self, label: str) -> str:
        taken = {entity.name for entity in self.entities}
        number = 1
        while f"{label} {number}" in taken:
            number += 1
        return f"{label} {number}"

    def next_color(self) -> tuple[float, float, float]:
        surfaces = sum(1 for entity in self.entities if not entity.is_body)
        return PALETTE[surfaces % len(PALETTE)]

    def add(self, entity: ModelEntity) -> ModelEntity:
        if self.get(entity.id) is not None:
            raise ValueError(f"model entity already exists: {entity.id}")
        self.entities.append(entity)
        self.revision += 1
        return entity

    def remove(self, entity_ids: str | tuple[str, ...] | list[str]) -> list[ModelEntity]:
        wanted = {entity_ids} if isinstance(entity_ids, str) else {str(value) for value in entity_ids}
        removed = [entity for entity in self.entities if entity.id in wanted]
        self.entities = [entity for entity in self.entities if entity.id not in wanted]
        self.selected_ids = [value for value in self.selected_ids if value not in wanted]
        if removed:
            self.revision += 1
        return removed

    def visible(self) -> list[ModelEntity]:
        return [entity for entity in self.entities if entity.visible]

    def set_visible(self, entity_id: str, visible: bool) -> bool:
        entity = self.get(entity_id)
        if entity is None or entity.visible == visible:
            return False
        entity.visible = visible
        self.revision += 1
        return True

    def snapshot(self) -> tuple[list[ModelEntity], list[str], int, Sketch]:
        """For undo: entities are replaced rather than edited, so a list copy is enough
        (visibility is the one field changed in place, so the entities are copied shallowly).
        The sketch is small and edited in place: it is copied whole."""

        from copy import copy

        return [copy(entity) for entity in self.entities], list(self.selected_ids), self.counter, self.sketch.copy()

    def restore(self, snapshot: tuple[list[ModelEntity], list[str], int, Sketch]) -> None:
        from copy import copy

        entities, selected, counter, sketch = snapshot
        self.entities = [copy(entity) for entity in entities]
        self.selected_ids = list(selected)
        self.counter = max(self.counter, counter)
        self.sketch = sketch.copy()
        self.selected_curve_ids = [value for value in self.selected_curve_ids if self.sketch.curve(value) is not None]
        self.revision += 1


def entity_from_result(
    document: ModelDocument,
    result: dict[str, Any],
    *,
    tool: str,
    params: dict[str, Any] | None = None,
    sources: tuple[str, ...] = (),
    name: str | None = None,
) -> ModelEntity:
    """A new entity (not yet added) from a kernel job's surface result."""

    kind = str(result.get("kind", "surface"))
    body = kind in ("shell", "solid")
    stats: dict[str, Any] = {
        key: result[key]
        for key in ("rms", "max_error", "area", "volume", "control_u", "control_v", "parameterization", "free_edges", "solid", "closed")
        if key in result
    }
    return ModelEntity(
        id=document.new_id(),
        name=name or document.next_name(KIND_LABELS.get(kind, kind.title())),
        kind=kind,
        tool=tool,
        brep=result["brep"],
        vertices=np.asarray(result["vertices"], dtype=float),
        triangles=np.asarray(result["triangles"], dtype=np.int64),
        edges=[np.asarray(edge, dtype=float) for edge in result.get("edges", [])],
        color=SOLID_COLOR if body else document.next_color(),
        params=dict(params or {}),
        stats=stats,
        sources=tuple(sources),
    )


__all__ = ("KIND_LABELS", "PALETTE", "SOLID_COLOR", "ModelDocument", "ModelEntity", "entity_from_result")
