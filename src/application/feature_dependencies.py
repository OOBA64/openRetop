"""Shared dependency planning and pruning for source-record deletion.

The helper deliberately coordinates existing state records only.  It does not
construct geometry, serialize projects, or touch the runtime CAD-object cache.
Controllers expose the returned BREP IDs so an infrastructure adapter can prune
that opaque cache at the same boundary.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from application.state import AppState


def _ids(values: Iterable[object]) -> set[str]:
    return {str(value) for value in values if str(value)}


@dataclass(frozen=True, slots=True)
class FeatureDependencyChange:
    """Existing records affected by deleting sources or generated surfaces."""

    removed_curve_ids: tuple[str, ...] = ()
    removed_preview_surface_ids: tuple[str, ...] = ()
    removed_brep_surface_ids: tuple[str, ...] = ()
    removed_loft_feature_ids: tuple[str, ...] = ()
    removed_four_boundary_feature_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "removed_curve_ids",
            "removed_preview_surface_ids",
            "removed_brep_surface_ids",
            "removed_loft_feature_ids",
            "removed_four_boundary_feature_ids",
        ):
            normalized = tuple(sorted(_ids(getattr(self, field_name))))
            object.__setattr__(self, field_name, normalized)

    @property
    def removed_surface_ids(self) -> tuple[str, ...]:
        return tuple(
            sorted(
                set(self.removed_preview_surface_ids)
                | set(self.removed_brep_surface_ids)
            )
        )

    @property
    def changed(self) -> bool:
        return any(
            (
                self.removed_curve_ids,
                self.removed_preview_surface_ids,
                self.removed_brep_surface_ids,
                self.removed_loft_feature_ids,
                self.removed_four_boundary_feature_ids,
            )
        )

    def as_metadata(self) -> Mapping[str, object]:
        return {
            "removed_curve_ids": self.removed_curve_ids,
            "removed_preview_surface_ids": self.removed_preview_surface_ids,
            "removed_brep_surface_ids": self.removed_brep_surface_ids,
            "removed_surface_ids": self.removed_surface_ids,
            "removed_loft_feature_ids": self.removed_loft_feature_ids,
            "removed_four_boundary_feature_ids": (
                self.removed_four_boundary_feature_ids
            ),
        }


def plan_feature_dependency_removal(
    state: AppState,
    *,
    curve_ids: Iterable[object] = (),
    preview_surface_ids: Iterable[object] = (),
    brep_surface_ids: Iterable[object] = (),
) -> FeatureDependencyChange:
    """Return the complete existing feature graph affected by source deletion."""

    if not isinstance(state, AppState):
        raise TypeError("state must be an AppState.")

    existing_curve_ids = {curve.id for curve in state.curve_collection.curves}
    existing_preview_ids = {
        surface.id for surface in state.surface_collection.surfaces
    }
    existing_brep_ids = {
        surface.id for surface in state.brep_surface_collection.surfaces
    }
    removed_curves = _ids(curve_ids) & existing_curve_ids
    removed_previews = _ids(preview_surface_ids) & existing_preview_ids
    removed_breps = _ids(brep_surface_ids) & existing_brep_ids

    if removed_curves:
        removed_previews.update(
            surface.id
            for surface in state.surface_collection.surfaces
            if removed_curves.intersection(surface.source_curve_ids)
        )
        removed_breps.update(
            surface.id
            for surface in state.brep_surface_collection.surfaces
            if removed_curves.intersection(surface.source_curve_ids)
        )

    removed_lofts: set[str] = set()
    removed_four_boundary: set[str] = set()
    changed = True
    while changed:
        before = (
            frozenset(removed_previews),
            frozenset(removed_breps),
            frozenset(removed_lofts),
            frozenset(removed_four_boundary),
        )
        for feature in state.loft_feature_collection.features:
            if (
                removed_curves.intersection(feature.options.source_curve_ids)
                or feature.preview_surface_id in removed_previews
                or feature.brep_surface_id in removed_breps
            ):
                removed_lofts.add(feature.id)
                if feature.preview_surface_id in existing_preview_ids:
                    removed_previews.add(feature.preview_surface_id)
                if feature.brep_surface_id in existing_brep_ids:
                    removed_breps.add(feature.brep_surface_id)

        for feature in state.four_boundary_feature_collection.features:
            if (
                removed_curves.intersection(feature.source_curve_ids)
                or feature.preview_surface_id in removed_previews
                or feature.brep_surface_id in removed_breps
            ):
                removed_four_boundary.add(feature.id)
                if feature.preview_surface_id in existing_preview_ids:
                    removed_previews.add(feature.preview_surface_id)
                if feature.brep_surface_id in existing_brep_ids:
                    removed_breps.add(feature.brep_surface_id)

        after = (
            frozenset(removed_previews),
            frozenset(removed_breps),
            frozenset(removed_lofts),
            frozenset(removed_four_boundary),
        )
        changed = after != before

    return FeatureDependencyChange(
        removed_curve_ids=tuple(removed_curves),
        removed_preview_surface_ids=tuple(removed_previews),
        removed_brep_surface_ids=tuple(removed_breps),
        removed_loft_feature_ids=tuple(removed_lofts),
        removed_four_boundary_feature_ids=tuple(removed_four_boundary),
    )


def prune_feature_dependencies(
    state: AppState,
    change: FeatureDependencyChange,
) -> FeatureDependencyChange:
    """Remove a planned dependency set while keeping collection state coherent."""

    if not isinstance(state, AppState):
        raise TypeError("state must be an AppState.")
    if not isinstance(change, FeatureDependencyChange):
        raise TypeError("change must be a FeatureDependencyChange.")

    preview_ids = set(change.removed_preview_surface_ids)
    brep_ids = set(change.removed_brep_surface_ids)
    loft_ids = set(change.removed_loft_feature_ids)
    four_boundary_ids = set(change.removed_four_boundary_feature_ids)

    state.surface_collection.surfaces = [
        surface
        for surface in state.surface_collection.surfaces
        if surface.id not in preview_ids
    ]
    remaining_preview_ids = {
        surface.id for surface in state.surface_collection.surfaces
    }
    state.surface_collection.selected_surface_ids.intersection_update(
        remaining_preview_ids
    )
    if state.surface_collection.active_surface_id not in remaining_preview_ids:
        state.surface_collection.active_surface_id = None
    for surface in state.surface_collection.surfaces:
        surface.selected = surface.id in state.surface_collection.selected_surface_ids

    state.brep_surface_collection.surfaces = [
        surface
        for surface in state.brep_surface_collection.surfaces
        if surface.id not in brep_ids
    ]
    remaining_brep_ids = {
        surface.id for surface in state.brep_surface_collection.surfaces
    }
    state.brep_surface_collection.selected_surface_ids.intersection_update(
        remaining_brep_ids
    )
    if state.brep_surface_collection.active_surface_id not in remaining_brep_ids:
        state.brep_surface_collection.active_surface_id = None
    for surface in state.brep_surface_collection.surfaces:
        surface.selected = (
            surface.id in state.brep_surface_collection.selected_surface_ids
        )

    state.loft_feature_collection.features = [
        feature
        for feature in state.loft_feature_collection.features
        if feature.id not in loft_ids
    ]
    remaining_loft_ids = {
        feature.id for feature in state.loft_feature_collection.features
    }
    if state.loft_feature_collection.active_feature_id not in remaining_loft_ids:
        state.loft_feature_collection.active_feature_id = (
            state.loft_feature_collection.features[0].id
            if state.loft_feature_collection.features
            else None
        )

    state.four_boundary_feature_collection.features = [
        feature
        for feature in state.four_boundary_feature_collection.features
        if feature.id not in four_boundary_ids
    ]
    remaining_four_boundary_ids = {
        feature.id
        for feature in state.four_boundary_feature_collection.features
    }
    if (
        state.four_boundary_feature_collection.active_feature_id
        not in remaining_four_boundary_ids
    ):
        state.four_boundary_feature_collection.active_feature_id = (
            state.four_boundary_feature_collection.features[0].id
            if state.four_boundary_feature_collection.features
            else None
        )
    return change


__all__ = (
    "FeatureDependencyChange",
    "plan_feature_dependency_removal",
    "prune_feature_dependencies",
)
