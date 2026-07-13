"""Editable loft feature state driven by persistent source curves."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class LoftFeatureOptions:
    source_curve_ids: list[str]
    source_order_locked: bool = True
    use_cad_wires: bool = True
    match_curve_directions: bool = True
    align_closed_curve_seams: bool = True
    preserve_corners: bool = True
    cap_start: bool = False
    cap_end: bool = False
    create_solid_if_closed: bool = False
    ruled: bool = False
    smoothing: str = "normal"
    rebuild_on_source_edit: bool = True
    overbuild_enabled: bool = True
    overbuild_amount: float = 0.10
    overbuild_u_start: float = 0.10
    overbuild_u_end: float = 0.10
    overbuild_v_start: float = 0.10
    overbuild_v_end: float = 0.10
    show_overbuild_handles: bool = True
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.source_curve_ids = [str(curve_id) for curve_id in self.source_curve_ids]
        self.source_order_locked = bool(self.source_order_locked)
        self.use_cad_wires = bool(self.use_cad_wires)
        self.match_curve_directions = bool(self.match_curve_directions)
        self.align_closed_curve_seams = bool(self.align_closed_curve_seams)
        self.preserve_corners = bool(self.preserve_corners)
        self.cap_start = bool(self.cap_start)
        self.cap_end = bool(self.cap_end)
        self.create_solid_if_closed = bool(self.create_solid_if_closed)
        self.ruled = bool(self.ruled)
        self.smoothing = str(self.smoothing or "normal")
        self.rebuild_on_source_edit = bool(self.rebuild_on_source_edit)
        self.overbuild_enabled = bool(self.overbuild_enabled)
        self.overbuild_amount = _overbuild_value(self.overbuild_amount)
        self.overbuild_u_start = _overbuild_value(self.overbuild_u_start)
        self.overbuild_u_end = _overbuild_value(self.overbuild_u_end)
        self.overbuild_v_start = _overbuild_value(self.overbuild_v_start)
        self.overbuild_v_end = _overbuild_value(self.overbuild_v_end)
        self.show_overbuild_handles = bool(self.show_overbuild_handles)
        self.metadata = dict(self.metadata) if isinstance(self.metadata, dict) else {}


def _overbuild_value(value: object) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.10
    if number != number or number in {float("inf"), float("-inf")}:
        number = 0.10
    return min(max(number, 0.0), 10.0)


@dataclass
class LoftFeatureRecord:
    id: str
    name: str
    options: LoftFeatureOptions
    brep_surface_id: str | None = None
    preview_surface_id: str | None = None
    last_build_success: bool = False
    last_build_reason: str = "Not built."
    last_build_warnings: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = str(self.id)
        self.name = str(self.name)
        self.brep_surface_id = (
            None if self.brep_surface_id is None else str(self.brep_surface_id)
        )
        self.preview_surface_id = (
            None if self.preview_surface_id is None else str(self.preview_surface_id)
        )
        self.last_build_success = bool(self.last_build_success)
        self.last_build_reason = str(self.last_build_reason)
        self.last_build_warnings = [str(value) for value in self.last_build_warnings]
        self.metadata = dict(self.metadata) if isinstance(self.metadata, dict) else {}
        self.metadata.setdefault("loft_feature_dirty", not self.last_build_success)


@dataclass
class LoftFeatureCollection:
    features: list[LoftFeatureRecord] = field(default_factory=list)
    active_feature_id: str | None = None


def add_loft_feature(
    collection: LoftFeatureCollection,
    feature: LoftFeatureRecord,
) -> LoftFeatureRecord:
    if any(existing.id == feature.id for existing in collection.features):
        raise ValueError(f"Loft feature already exists: {feature.id}")
    collection.features.append(feature)
    collection.active_feature_id = feature.id
    return feature


def remove_loft_feature(
    collection: LoftFeatureCollection,
    feature_id: str,
) -> LoftFeatureRecord | None:
    for index, feature in enumerate(collection.features):
        if feature.id != feature_id:
            continue
        removed = collection.features.pop(index)
        if collection.active_feature_id == feature_id:
            collection.active_feature_id = (
                collection.features[0].id if collection.features else None
            )
        return removed
    return None


def loft_feature_for_brep_surface(
    collection: LoftFeatureCollection,
    brep_surface_id: str,
) -> LoftFeatureRecord | None:
    return next(
        (
            feature
            for feature in collection.features
            if feature.brep_surface_id == brep_surface_id
        ),
        None,
    )


def mark_loft_features_dirty_for_curve(
    collection: LoftFeatureCollection,
    curve_id: str,
) -> list[LoftFeatureRecord]:
    changed: list[LoftFeatureRecord] = []
    for feature in collection.features:
        if str(curve_id) not in feature.options.source_curve_ids:
            continue
        feature.metadata["loft_feature_dirty"] = True
        feature.metadata["source_edit_revision"] = int(
            feature.metadata.get("source_edit_revision", 0)
        ) + 1
        changed.append(feature)
    return changed
