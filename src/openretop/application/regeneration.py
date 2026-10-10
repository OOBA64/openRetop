"""Replaying the design history in the kernel worker (P-01).

``regenerate`` runs the timeline's features from one of them to the end. Features before it
start from their last results, so editing a late feature costs only the features after it;
after a project is opened there are no results yet, and the whole history replays.

A feature the kernel cannot build is marked failed with the kernel's reason; the features
after it that change the same body are skipped (the body shows its state before the
failure), and the rest of the history still runs, as in Fusion's timeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openretop.modeling.document import ModelDocument, ModelEntity, entity_from_result
from openretop.modeling.timeline import Feature


@dataclass(frozen=True)
class RegenReport:
    replayed: int
    failed: tuple[tuple[str, str], ...] = ()  # (feature name, why)

    @property
    def ok(self) -> bool:
        return not self.failed

    def summary(self) -> str:
        if self.ok:
            return f"Rebuilt {self.replayed} feature(s)"
        names = "; ".join(f"{name}: {why}" for name, why in self.failed)
        return f"Rebuilt with {len(self.failed)} failed feature(s) - {names}"


def extrude_ranges(inputs: dict[str, Any], loop_count: int) -> list[tuple[float, float]]:
    """Per loop of the sketch: (low, high) along its normal. Holes measured on the scan keep
    their own range while the sketch has the loop they were measured for."""

    low, high = -float(inputs.get("back", 0.0)), float(inputs.get("front", 0.0))
    holes = {int(key): value for key, value in (inputs.get("holes") or {}).items()}
    ranges = []
    for index in range(loop_count):
        hole = holes.get(index) if inputs.get("auto", True) else None
        ranges.append((max(low, float(hole[0])), min(high, float(hole[1]))) if hole is not None else (low, high))
    return ranges


def regenerate(model: ModelDocument, worker: Any, start: str | None = None) -> RegenReport:
    """Replay the features from ``start`` (a feature id; None: from the first) to the end."""

    timeline = model.timeline
    features = timeline.features
    first = 0 if start is None else timeline.index(start)
    bodies: dict[str, dict[str, Any]] = {}
    for feature in features[:first]:
        if feature.kind == "sketch" or feature.status != "ok":
            continue
        if feature.result is None:  # never built in this session (just opened): replay it all
            return regenerate(model, worker, None)
        bodies[feature.entity] = feature.result
    failed: list[tuple[str, str]] = []
    broken: dict[str, str] = {}  # body -> the feature that failed on it
    for feature in features[first:]:
        if feature.kind != "sketch" and feature.entity in broken:
            _mark(feature, "skipped", f"after {broken[feature.entity]} failed")
            continue
        reply_ok, value, error = _run(feature, timeline, bodies, worker)
        if reply_ok:
            _mark(feature, "ok", "")
            feature.result = value
            if feature.kind != "sketch":
                bodies[feature.entity] = value
        else:
            _mark(feature, "failed", error)
            feature.result = None
            failed.append((feature.name, error))
            if feature.kind != "sketch":
                broken[feature.entity] = feature.name
    _write_entities(model, features[first:], bodies)
    return RegenReport(len(features) - first, tuple(failed))


def _mark(feature: Feature, status: str, message: str) -> None:
    feature.status, feature.message = status, message


def _run(feature: Feature, timeline: Any, bodies: dict[str, dict[str, Any]], worker: Any) -> tuple[bool, Any, str]:
    inputs = feature.inputs
    if feature.kind == "sketch":
        reply = worker.call("profile", inputs["frame"], inputs["loops"], rms=inputs.get("rms", 0.0), max_error=inputs.get("max_error", 0.0))
    elif feature.kind == "base":
        reply = worker.call("shape", inputs["brep"], kind=str(inputs.get("kind", "solid")))
    else:
        sketch = timeline.get(str(inputs.get("sketch", "")))
        if sketch is None:
            return False, None, "its sketch was deleted"
        if sketch.status != "ok":
            return False, None, f"its sketch ({sketch.name}) failed"
        mode = str(inputs.get("mode", "new"))
        target = bodies.get(feature.entity) if mode != "new" else None
        if mode != "new" and target is None:
            return False, None, "there is no body to add to or cut from"
        loops = sketch.inputs["loops"]
        if inputs.get("regions") and "sketch2d" in sketch.inputs:
            from openretop.modeling.sketch2d import Sketch2D
            from openretop.modeling.sketch_profiles import find_profiles

            picked = find_profiles(Sketch2D.from_dict(sketch.inputs["sketch2d"])).loops_for(list(inputs["regions"]))
            if picked is None:
                return False, None, "a region it extruded is no longer closed in the sketch"
            loops = picked
        reply = worker.call(
            "extrude",
            sketch.inputs["frame"],
            loops,
            extrude_ranges(inputs, len(loops)),
            draft=float(inputs.get("draft", 0.0)),
            mode=mode,
            target=None if target is None else target["brep"],
        )
    return bool(reply.ok), reply.value, str(reply.error)


def _write_entities(model: ModelDocument, replayed: list[Feature], bodies: dict[str, dict[str, Any]]) -> None:
    """Bring the entities the replayed features make up to date (ids, names, colours and
    visibility stay; a body shows its last good state)."""

    for feature in replayed:
        if feature.kind == "sketch" and feature.result is not None:
            tool = "sketch2d" if "sketch2d" in feature.inputs else "section"
            replace_entity(model, feature.entity, feature.result, tool=tool, params=feature.inputs)
    for body_id in dict.fromkeys(feature.entity for feature in replayed if feature.kind != "sketch"):
        state = bodies.get(body_id)
        if state is not None:
            last = [feature for feature in model.timeline.body_features(body_id) if feature.status == "ok"][-1]
            replace_entity(model, body_id, state, tool=last.kind if last.kind != "base" else "base", params=last.inputs if last.kind != "base" else {})
    model.revision += 1


def replace_entity(model: ModelDocument, entity_id: str, result: dict[str, Any], *, tool: str, params: dict[str, Any]) -> ModelEntity:
    """The entity ``entity_id`` remade from a kernel result, in its place in the model."""

    fresh = entity_from_result(model, result, tool=tool, params={key: value for key, value in params.items() if key != "brep"})
    old = model.get(entity_id)
    fresh.id = entity_id
    if old is None:
        model.entities.append(fresh)
        return fresh
    fresh.name, fresh.color, fresh.visible, fresh.sources = old.name, old.color, old.visible, old.sources
    model.entities[model.entities.index(old)] = fresh
    return fresh


__all__ = ("RegenReport", "extrude_ranges", "regenerate", "replace_entity")
