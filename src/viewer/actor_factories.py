"""Registry and renderer adapter for focused VTK actor factories."""

from __future__ import annotations

from viewer.curve_actors import (
    create_curve_actor,
    create_section_result_actor,
    update_curve_actor,
    update_section_result_actor,
)
from viewer.mesh_actors import create_mesh_actor, update_mesh_actor
from viewer.picking_service import PickingService
from viewer.region_actors import create_region_actor, update_region_actor
from viewer.section_actors import create_section_plane_actor, update_section_plane_actor
from viewer.style_conversion import apply_actor_style, set_actor_visibility
from viewer.surface_actors import create_surface_actor, update_surface_actor
from viewer.vtk_actor_utils import vtk_matrix


class VTKActorAdapter:
    """Concrete SceneSynchronizer adapter using only public VTK actors."""

    def __init__(self, renderer: object, picking: PickingService | None = None) -> None:
        self.renderer = renderer
        self.picking = picking

    def create_actor(self, category: str, item: object) -> object:
        item_id = str(getattr(item, "id", "<unknown>"))
        try:
            actor = _factory(category)(item)
            self.renderer.AddActor(actor)
            if self.picking is not None:
                self.picking.register_actor(
                    actor,
                    object_id=item_id,
                    object_type=category,
                )
            return actor
        except Exception as exc:
            raise RuntimeError(
                f"Failed to create {category} actor for scene item {item_id}: {exc}"
            ) from exc

    def update_geometry(self, actor: object, category: str, item: object) -> None:
        item_id = str(getattr(item, "id", "<unknown>"))
        try:
            _updater(category)(actor, item)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to update {category} geometry for scene item {item_id}: {exc}"
            ) from exc

    def update_style(self, actor: object, category: str, item: object) -> None:
        item_id = str(getattr(item, "id", "<unknown>"))
        try:
            apply_actor_style(actor, getattr(item, "style"))
        except Exception as exc:
            raise RuntimeError(
                f"Failed to update {category} style for scene item {item_id}: {exc}"
            ) from exc

    def update_transform(self, actor: object, category: str, item: object) -> None:
        transform = getattr(item, "transform", None)
        if transform is None:
            return
        item_id = str(getattr(item, "id", "<unknown>"))
        try:
            actor.SetUserMatrix(vtk_matrix(transform))
        except Exception as exc:
            raise RuntimeError(
                f"Failed to update {category} transform for scene item {item_id}: {exc}"
            ) from exc

    def set_visibility(self, actor: object, visible: bool) -> None:
        set_actor_visibility(actor, visible)

    def remove_actor(self, actor: object) -> None:
        if self.picking is not None:
            self.picking.unregister_actor(actor)
        self.renderer.RemoveActor(actor)


def _factory(category: str):
    factories = {
        "mesh": create_mesh_actor,
        "curve": create_curve_actor,
        "surface": create_surface_actor,
        "region": create_region_actor,
        "section_plane": create_section_plane_actor,
        "section_result": create_section_result_actor,
    }
    try:
        return factories[category]
    except KeyError as exc:
        raise ValueError(f"Unsupported actor category: {category}") from exc


def _updater(category: str):
    updaters = {
        "mesh": update_mesh_actor,
        "curve": update_curve_actor,
        "surface": update_surface_actor,
        "region": update_region_actor,
        "section_plane": update_section_plane_actor,
        "section_result": update_section_result_actor,
    }
    try:
        return updaters[category]
    except KeyError as exc:
        raise ValueError(f"Unsupported actor category: {category}") from exc


__all__ = ("VTKActorAdapter",)
