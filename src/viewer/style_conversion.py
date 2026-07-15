"""Convert toolkit-neutral display styles to VTK actor properties."""

from __future__ import annotations

from viewer.scene_types import DisplayStyleSnapshot


def apply_actor_style(actor: object, style: DisplayStyleSnapshot) -> None:
    prop = actor.GetProperty()
    prop.SetColor(*style.color)
    prop.SetOpacity(float(style.opacity))
    prop.SetLineWidth(float(style.line_width))
    prop.SetPointSize(float(style.point_size))
    if style.edge_color is not None:
        prop.SetEdgeColor(*style.edge_color)
    prop.SetEdgeVisibility(1 if style.edge_visibility else 0)
    representation = str(style.representation).lower()
    if representation == "wireframe":
        prop.SetRepresentationToWireframe()
    elif representation == "points":
        prop.SetRepresentationToPoints()
    else:
        prop.SetRepresentationToSurface()


def set_actor_visibility(actor: object, visible: bool) -> None:
    actor.SetVisibility(1 if visible else 0)


__all__ = ("apply_actor_style", "set_actor_visibility")
