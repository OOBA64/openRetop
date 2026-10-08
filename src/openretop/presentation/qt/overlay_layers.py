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


def create_over_scene_layer(main_renderer: object) -> tuple[object, int] | None:
    """A new 3D layer drawn over the scene, sharing its camera; None if there is no render window."""

    window = main_renderer.GetRenderWindow()  # type: ignore[attr-defined]
    if window is None:
        return None
    from vtkmodules.vtkRenderingCore import vtkRenderer

    layer_renderer = vtkRenderer()
    layer_renderer.SetActiveCamera(main_renderer.GetActiveCamera())  # type: ignore[attr-defined]  # one camera: always in sync
    layer = attach_overlay_renderer(window, main_renderer, layer_renderer, over_scene=True)
    return layer_renderer, layer


class ImageOverlay:
    """A transparent renderer in its own layer showing one RGBA image 1:1."""

    def __init__(self, render_window: object, main_renderer: object) -> None:
        from vtkmodules.vtkCommonDataModel import vtkImageData
        from vtkmodules.vtkRenderingCore import vtkImageActor, vtkRenderer

        self.render_window = render_window
        self.image = vtkImageData()
        self.actor = vtkImageActor()
        self.actor.SetInputData(self.image)
        self.actor.InterpolateOn()  # harmless when pixel-aligned, smooth if the scale is fractional
        self.actor.PickableOff()
        self.actor.DragableOff()
        self.renderer = vtkRenderer()
        self.renderer.SetDraw(False)
        self.renderer.AddViewProp(self.actor)
        self.renderer.GetActiveCamera().ParallelProjectionOn()
        attach_overlay_renderer(render_window, main_renderer, self.renderer)
        self._size = (0, 0)

    def set_viewport(self, viewport: tuple[float, float, float, float]) -> None:
        self.renderer.SetViewport(*viewport)

    def set_image(self, rgba: object, width: int, height: int) -> None:
        """``rgba`` is a (height, width, 4) uint8 array, top row first."""

        import numpy as np
        from vtkmodules import vtkCommonCore
        from vtkmodules.util.numpy_support import numpy_to_vtk

        flipped = np.ascontiguousarray(np.asarray(rgba, dtype=np.uint8)[::-1])  # VTK rows start at the bottom
        scalars = numpy_to_vtk(flipped.reshape(-1, 4), deep=True, array_type=vtkCommonCore.VTK_UNSIGNED_CHAR)
        scalars.SetName("rgba")
        self.image.SetDimensions(width, height, 1)
        self.image.GetPointData().SetScalars(scalars)
        self.image.Modified()
        if self._size != (width, height):
            self._size = (width, height)
            camera = self.renderer.GetActiveCamera()
            # Image pixel i is centred on world coordinate i, so the visible range must be
            # [-0.5, size - 0.5]; centring on size / 2 would put every display pixel on the
            # boundary between two image pixels and make glyph rows round unevenly.
            centre_x, centre_y = (width - 1) / 2.0, (height - 1) / 2.0
            camera.SetFocalPoint(centre_x, centre_y, 0.0)
            camera.SetPosition(centre_x, centre_y, 10.0 * max(width, height))
            camera.SetViewUp(0.0, 1.0, 0.0)
            camera.SetParallelScale(height / 2.0)
            camera.SetClippingRange(1.0, 100.0 * max(width, height))

    def set_draw(self, draw: bool) -> None:
        self.renderer.SetDraw(bool(draw))

    def attached(self) -> bool:
        return any(renderer is self.renderer for renderer in render_window_renderers(self.render_window))

    def close(self) -> None:
        try:
            self.renderer.SetDraw(False)
            if not bool(self.render_window.GetNeverRendered()):  # type: ignore[attr-defined]
                self.renderer.ReleaseGraphicsResources(self.render_window)
            self.render_window.RemoveRenderer(self.renderer)  # type: ignore[attr-defined]
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass


__all__ = ("ImageOverlay", "attach_overlay_renderer", "create_over_scene_layer", "next_overlay_layer", "render_window_renderers")
