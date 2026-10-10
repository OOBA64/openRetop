"""The design history (P-01): the features that made the solid model, in order.

A feature is plain data: what it is, its inputs, and the model entity it makes or changes.

- ``sketch``: a section sketch (lines and arcs on a plane); makes a profile entity.
- ``extrude``: a sketch's profile extruded as a new body, or added to / cut from a body.
- ``base``: a body the history did not make (a surface sewn in the Surface workspace, a body
  from an older project), kept as its exact geometry at the moment a feature first used it.

Bodies keep their entity id through the features that change them, so "Body 1" is one
thing from its first extrude to its last cut. Regeneration (``application.regeneration``)
replays the features in the kernel worker; each feature keeps its last result (``result``,
not saved) so an edit replays only from the edited feature on.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

FEATURE_KINDS = ("sketch", "extrude", "base")
KIND_TITLES = {"sketch": "Sketch", "extrude": "Extrude", "base": "Base Body"}


@dataclass
class Feature:
    id: str
    kind: str
    name: str
    entity: str  # the model entity it makes (sketch: its profile) or changes (a body)
    inputs: dict[str, Any] = field(default_factory=dict)
    status: str = "ok"  # ok, failed (the kernel said why: ``message``), skipped (after a failure)
    message: str = ""
    result: dict[str, Any] | None = field(default=None, compare=False, repr=False)

    def reads(self) -> tuple[str, ...]:
        """Ids of the earlier features whose output this one uses."""

        return (str(self.inputs["sketch"]),) if self.kind == "extrude" and self.inputs.get("sketch") else ()


@dataclass
class Timeline:
    features: list[Feature] = field(default_factory=list)
    counter: int = 0

    def new_id(self) -> str:
        self.counter += 1
        return f"feature-{self.counter}"

    def next_name(self, kind: str) -> str:
        title = KIND_TITLES.get(kind, kind.title())
        taken = {feature.name for feature in self.features}
        number = 1
        while f"{title} {number}" in taken:
            number += 1
        return f"{title} {number}"

    def add(self, kind: str, entity: str, inputs: dict[str, Any], *, result: dict[str, Any] | None = None, name: str | None = None) -> Feature:
        if kind not in FEATURE_KINDS:
            raise ValueError(f"unknown feature kind: {kind}")
        feature = Feature(self.new_id(), kind, name or self.next_name(kind), entity, dict(inputs), result=result)
        self.features.append(feature)
        return feature

    def get(self, feature_id: str) -> Feature | None:
        return next((feature for feature in self.features if feature.id == feature_id), None)

    def index(self, feature_id: str) -> int:
        return next(number for number, feature in enumerate(self.features) if feature.id == feature_id)

    def maker(self, entity_id: str) -> Feature | None:
        """The feature that made a sketch's profile entity."""

        return next((feature for feature in self.features if feature.kind == "sketch" and feature.entity == entity_id), None)

    def body_features(self, body_id: str) -> list[Feature]:
        return [feature for feature in self.features if feature.kind != "sketch" and feature.entity == body_id]

    def has(self, entity_id: str) -> bool:
        return any(feature.entity == entity_id for feature in self.features)

    def users(self, feature_id: str) -> list[Feature]:
        return [feature for feature in self.features if feature_id in feature.reads()]

    def copy(self) -> Timeline:
        """For undo: features are copied; kernel results (immutable once made) are shared."""

        features = []
        for feature in self.features:
            duplicate = copy.copy(feature)
            duplicate.inputs = copy.deepcopy(feature.inputs)
            features.append(duplicate)
        return Timeline(features, self.counter)

    # -- persistence (base bodies' BREP is packed by ``modeling.persistence``) ------------------

    def to_dict(self, pack_bytes: Any) -> dict[str, Any]:
        def inputs(feature: Feature) -> dict[str, Any]:
            data = dict(feature.inputs)
            if feature.kind == "base":
                data["brep"] = pack_bytes(data["brep"])
            return data

        return {
            "counter": self.counter,
            "features": [
                {"id": feature.id, "kind": feature.kind, "name": feature.name, "entity": feature.entity, "inputs": inputs(feature), "status": feature.status, "message": feature.message}
                for feature in self.features
            ],
        }

    @classmethod
    def from_dict(cls, data: Any, unpack_bytes: Any) -> Timeline:
        timeline = cls()
        if not isinstance(data, dict):
            return timeline
        for item in data.get("features", []):
            inputs = dict(item.get("inputs", {}))
            if item["kind"] == "base":
                inputs["brep"] = unpack_bytes(inputs["brep"])
            timeline.features.append(
                Feature(str(item["id"]), str(item["kind"]), str(item["name"]), str(item["entity"]), inputs, str(item.get("status", "ok")), str(item.get("message", "")))
            )
        timeline.counter = max(int(data.get("counter", 0)), len(timeline.features))
        return timeline


__all__ = ("FEATURE_KINDS", "KIND_TITLES", "Feature", "Timeline")
