"""Editable four-boundary patch feature records."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class FourBoundaryPatchFeatureRecord:
    id: str
    name: str
    source_curve_ids: list[str]
    preserve_corners: bool = True
    match_directions: bool = True
    fill_method: str = "coons_preview"
    brep_surface_id: str | None = None
    preview_surface_id: str | None = None
    last_build_status: str = "Not built."
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.name = str(self.name)
        self.source_curve_ids = [str(curve_id) for curve_id in self.source_curve_ids]
        self.preserve_corners = bool(self.preserve_corners)
        self.match_directions = bool(self.match_directions)
        self.fill_method = str(self.fill_method or "coons_preview")
        self.brep_surface_id = (
            None if self.brep_surface_id is None else str(self.brep_surface_id)
        )
        self.preview_surface_id = (
            None if self.preview_surface_id is None else str(self.preview_surface_id)
        )
        self.last_build_status = str(self.last_build_status)
        self.metadata = dict(self.metadata) if isinstance(self.metadata, dict) else {}
        self.metadata.setdefault("four_boundary_feature_dirty", False)


@dataclass
class FourBoundaryPatchFeatureCollection:
    features: list[FourBoundaryPatchFeatureRecord] = field(default_factory=list)
    active_feature_id: str | None = None


def add_four_boundary_feature(
    collection: FourBoundaryPatchFeatureCollection,
    feature: FourBoundaryPatchFeatureRecord,
) -> FourBoundaryPatchFeatureRecord:
    if any(existing.id == feature.id for existing in collection.features):
        raise ValueError(f"Four-boundary feature already exists: {feature.id}")
    collection.features.append(feature)
    collection.active_feature_id = feature.id
    return feature


def mark_four_boundary_features_dirty_for_curve(
    collection: FourBoundaryPatchFeatureCollection,
    curve_id: str,
) -> list[FourBoundaryPatchFeatureRecord]:
    changed: list[FourBoundaryPatchFeatureRecord] = []
    for feature in collection.features:
        if str(curve_id) not in feature.source_curve_ids:
            continue
        feature.metadata["four_boundary_feature_dirty"] = True
        changed.append(feature)
    return changed
