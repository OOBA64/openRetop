"""Helpers for transparent overlay renderers stacked above the scene in one render window."""

from __future__ import annotations


def render_window_renderers(render_window: object) -> tuple[object, ...]:
    collection = render_window.GetRenderers()  # type: ignore[attr-defined]
    collection.InitTraversal()
    result: list[object] = []
    while True:
        renderer = collection.GetNextItem()
        if renderer is None:
            break
        result.append(renderer)
    return tuple(result)


def next_overlay_layer(render_window: object, main_renderer: object) -> int:
    """The lowest layer above the scene that no other renderer uses."""

    occupied = {
        int(renderer.GetLayer())  # type: ignore[attr-defined]
        for renderer in render_window_renderers(render_window)
        if renderer is not main_renderer
    }
    layer = 1
    while layer in occupied:
        layer += 1
    return layer


def attach_overlay_renderer(
    render_window: object,
    main_renderer: object,
    overlay: object,
    *,
    over_scene: bool = False,
) -> int:
    """Configure ``overlay`` as a transparent, non-interactive layer above ``main_renderer``.

    The overlay keeps the colour already drawn.  With ``over_scene`` its props are 3D and must
    never be hidden by (or intersect) the scene: the depth buffer is cleared before it draws.
    VTK ties that clear to the renderer's Erase flag, so Erase must stay ON for such a layer
    (the preserved colour buffer is still not cleared); flat 2D overlays can switch it off.
    Returns the layer it was given.
    """

    overlay.InteractiveOff()  # type: ignore[attr-defined]
    overlay.SetBackgroundAlpha(0.0)  # type: ignore[attr-defined]
    overlay.SetPreserveColorBuffer(True)  # type: ignore[attr-defined]
    overlay.SetPreserveDepthBuffer(False)  # type: ignore[attr-defined]
    if over_scene:
        overlay.EraseOn()  # type: ignore[attr-defined]
    else:
        overlay.EraseOff()  # type: ignore[attr-defined]
    layer = next_overlay_layer(render_window, main_renderer)
    overlay.SetLayer(layer)  # type: ignore[attr-defined]
    if int(render_window.GetNumberOfLayers()) < layer + 1:  # type: ignore[attr-defined]
        render_window.SetNumberOfLayers(layer + 1)  # type: ignore[attr-defined]
    render_window.AddRenderer(overlay)  # type: ignore[attr-defined]
    return layer


__all__ = ("attach_overlay_renderer", "next_overlay_layer", "render_window_renderers")
