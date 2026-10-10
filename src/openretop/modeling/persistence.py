"""The model (surfaces, bodies, 3D Sketch) in the project file (S-12).

Stored as one JSON object under the project's ``model`` key. Geometry is exact BREP plus the
display mesh and edges, each zlib-compressed and base64-encoded, so a project reopens with no
kernel work and nothing to re-tessellate. Older versions of the app keep the key untouched
(unknown top-level keys round-trip through the project file).
"""

from __future__ import annotations

import base64
import io
import zlib
from typing import Any

import numpy as np

from openretop.modeling.document import ModelDocument, ModelEntity
from openretop.modeling.sketch import Sketch, SketchCurve
from openretop.modeling.timeline import Timeline

FORMAT = 1
PROJECT_KEY = "model"


def _pack_bytes(data: bytes) -> str:
    return base64.b64encode(zlib.compress(data, 6)).decode("ascii")


def _unpack_bytes(text: str) -> bytes:
    return zlib.decompress(base64.b64decode(text.encode("ascii")))


def _pack_arrays(**arrays: np.ndarray) -> str:
    buffer = io.BytesIO()
    np.savez(buffer, **arrays)  # type: ignore[arg-type]
    return _pack_bytes(buffer.getvalue())


def _unpack_arrays(text: str) -> dict[str, np.ndarray]:
    with np.load(io.BytesIO(_unpack_bytes(text)), allow_pickle=False) as data:
        return {name: data[name] for name in data.files}


def _plain(value: Any) -> Any:
    """JSON-safe copy of tool parameters and statistics."""

    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.floating, np.integer, np.bool_)):
        return value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def model_to_dict(document: ModelDocument) -> dict[str, Any] | None:
    """The model as JSON-ready data, or None when there is nothing to keep."""

    if not document.entities and not document.sketch.curves:
        return None
    entities = []
    for entity in document.entities:
        edges = [np.asarray(edge, dtype=np.float32).reshape(-1, 3) for edge in entity.edges]
        edge_offsets = np.cumsum([0] + [len(edge) for edge in edges]).astype(np.int64)
        entities.append(
            {
                "id": entity.id,
                "name": entity.name,
                "kind": entity.kind,
                "tool": entity.tool,
                "color": [float(value) for value in entity.color],
                "visible": bool(entity.visible),
                "params": _plain(entity.params),
                "stats": _plain(entity.stats),
                "sources": list(entity.sources),
                "brep": _pack_bytes(entity.brep),
                "mesh": _pack_arrays(
                    vertices=np.asarray(entity.vertices, dtype=np.float32),
                    triangles=np.asarray(entity.triangles, dtype=np.int32),
                    edge_points=np.vstack(edges) if edges else np.zeros((0, 3), dtype=np.float32),
                    edge_offsets=edge_offsets,
                ),
            }
        )
    sketch = document.sketch
    return {
        "format": FORMAT,
        "counter": int(document.counter),
        "entities": entities,
        "timeline": _plain(document.timeline.to_dict(_pack_bytes)),
        "sketch": {
            "counter": int(sketch.counter),
            "nodes": {node: [float(v) for v in position] for node, position in sketch.nodes.items()},
            "curves": [
                {
                    "id": curve.id,
                    "name": curve.name,
                    "nodes": list(curve.nodes),
                    "closed": bool(curve.closed),
                    "visible": bool(curve.visible),
                    "smoothness": float(curve.smoothness),
                    "feature": bool(curve.feature),
                    "polyline": _pack_arrays(points=np.asarray(curve.polyline, dtype=np.float64)),
                }
                for curve in sketch.curves
            ],
        },
    }


def model_from_dict(data: object) -> tuple[ModelDocument, list[str]]:
    """The model back from the project (and warnings about anything that could not be read)."""

    document = ModelDocument()
    warnings: list[str] = []
    if not isinstance(data, dict):
        return document, warnings
    if int(data.get("format", 0)) > FORMAT:
        warnings.append("The model was saved by a newer version of openRetop and may be incomplete.")
    for index, item in enumerate(data.get("entities", [])):
        try:
            mesh = _unpack_arrays(item["mesh"])
            offsets = mesh["edge_offsets"]
            points = mesh["edge_points"].astype(float)
            edges = [points[offsets[k] : offsets[k + 1]] for k in range(len(offsets) - 1)]
            document.entities.append(
                ModelEntity(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    kind=str(item["kind"]),
                    tool=str(item.get("tool", "")),
                    brep=_unpack_bytes(item["brep"]),
                    vertices=mesh["vertices"].astype(float),
                    triangles=mesh["triangles"].astype(np.int64),
                    edges=edges,
                    color=tuple(float(value) for value in item.get("color", (0.36, 0.62, 0.95)))[:3],  # type: ignore[arg-type]
                    visible=bool(item.get("visible", True)),
                    params=dict(item.get("params", {})),
                    stats=dict(item.get("stats", {})),
                    sources=tuple(str(value) for value in item.get("sources", ())),
                )
            )
        except (KeyError, TypeError, ValueError, zlib.error, OSError) as exc:
            warnings.append(f"Model item {index + 1} could not be read and was skipped ({exc}).")
    document.counter = max(int(data.get("counter", 0)), len(document.entities))
    sketch_data = data.get("sketch") or {}
    sketch = Sketch()
    try:
        sketch.nodes = {str(node): np.asarray(position, dtype=float).reshape(3) for node, position in sketch_data.get("nodes", {}).items()}
        for item in sketch_data.get("curves", []):
            nodes = [str(node) for node in item["nodes"]]
            if not all(node in sketch.nodes for node in nodes):
                warnings.append(f"Sketch curve {item.get('name', '?')} refers to missing points and was skipped.")
                continue
            sketch.curves.append(
                SketchCurve(
                    id=str(item["id"]),
                    name=str(item["name"]),
                    nodes=nodes,
                    closed=bool(item.get("closed", False)),
                    polyline=_unpack_arrays(item["polyline"])["points"].astype(float),
                    visible=bool(item.get("visible", True)),
                    smoothness=float(item.get("smoothness", 0.5)),
                    feature=bool(item.get("feature", False)),
                )
            )
        sketch.counter = int(sketch_data.get("counter", len(sketch.nodes) + len(sketch.curves)))
    except (KeyError, TypeError, ValueError, zlib.error, OSError) as exc:
        warnings.append(f"The 3D Sketch could not be read ({exc}).")
        sketch = Sketch()
    document.sketch = sketch
    try:
        document.timeline = Timeline.from_dict(data.get("timeline"), _unpack_bytes)
    except (KeyError, TypeError, ValueError, zlib.error) as exc:
        warnings.append(f"The design history could not be read; the model keeps its shapes but cannot be rebuilt ({exc}).")
    entity_ids = {entity.id for entity in document.entities}
    lost = [feature.name for feature in document.timeline.features if feature.entity not in entity_ids]
    if lost:
        document.timeline.features = [feature for feature in document.timeline.features if feature.entity in entity_ids]
        warnings.append(f"History features without their model item were dropped: {', '.join(lost)}.")
    return document, warnings


__all__ = ("FORMAT", "PROJECT_KEY", "model_from_dict", "model_to_dict")
