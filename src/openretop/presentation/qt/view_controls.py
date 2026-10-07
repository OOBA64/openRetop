"""Viewport navigation overlay: the view cube drawn inside the VTK frame.

QVTK renders into a native OpenGL window, and a Qt child widget cannot be drawn over it.
So the cube is painted by Qt into an image (``ViewCubeWidget.render_image``), shown by a
transparent, non-interactive overlay renderer in the same render window, and the
viewport forwards mouse events here for hover and clicks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QPointF, Qt, Signal
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QWidget

from openretop.presentation.qt.view_cube import (
    CUBE_MARGIN,
    CUBE_WIDGET_SIZE,
    ViewCubeWidget,
    normalized_camera_orientation,
)


@dataclass(frozen=True, slots=True)
class NavigationClusterDiagnosticState:
    cube_visible: bool
    axes_visible: bool
    overlay_attached: bool
    overlay_viewport: tuple[float, float, float, float] | None
    camera_signature: tuple[float, ...] | None
    observer_count: int
    camera_update_count: int
    image_update_count: int
    logical_bounds: tuple[int, int, int, int]
    last_error: str | None


def normalized_cube_viewport(
    width: object,
    height: object,
    device_pixel_ratio: object = 1.0,
) -> tuple[float, float, float, float] | None:
    """Top-right normalized VTK viewport (x0, y0, x1, y1) for the cube, or None."""

    try:
        pixel_width, pixel_height, ratio = float(width), float(height), float(device_pixel_ratio)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(value) for value in (pixel_width, pixel_height, ratio)):
        return None
    if pixel_width <= 0.0 or pixel_height <= 0.0:
        return None
    ratio = ratio if ratio > 0.0 else 1.0
    size = min(CUBE_WIDGET_SIZE * ratio, pixel_width, pixel_height)
    margin = CUBE_MARGIN * ratio
    left = max(pixel_width - size - margin, 0.0)
    top = min(margin, max(pixel_height - size, 0.0))
    x0, x1 = left / pixel_width, (left + size) / pixel_width
    y1 = (pixel_height - top) / pixel_height
    y0 = (pixel_height - top - size) / pixel_height
    return (x0, max(y0, 0.0), min(x1, 1.0), min(y1, 1.0))


class _CubeImageOverlay:
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
        self.renderer.InteractiveOff()
        self.renderer.SetBackgroundAlpha(0.0)
        self.renderer.SetPreserveColorBuffer(True)
        self.renderer.SetPreserveDepthBuffer(False)
        self.renderer.EraseOff()
        self.renderer.SetDraw(False)
        self.renderer.AddViewProp(self.actor)
        camera = self.renderer.GetActiveCamera()
        camera.ParallelProjectionOn()
        occupied = {
            int(renderer.GetLayer())
            for renderer in _renderers(render_window)
            if renderer is not main_renderer
        }
        layer = 1
        while layer in occupied:
            layer += 1
        self.renderer.SetLayer(layer)
        if int(render_window.GetNumberOfLayers()) < layer + 1:
            render_window.SetNumberOfLayers(layer + 1)
        render_window.AddRenderer(self.renderer)
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
        return any(renderer is self.renderer for renderer in _renderers(self.render_window))

    def close(self) -> None:
        try:
            self.renderer.SetDraw(False)
            if not bool(self.render_window.GetNeverRendered()):
                self.renderer.ReleaseGraphicsResources(self.render_window)
            self.render_window.RemoveRenderer(self.renderer)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            pass


class ViewportNavigationCluster(QObject):
    """Top-right view cube and axis balls that follow the main camera.

    The QVTK render window stays the only native window and its interactor the only
    input owner; this class observes interaction events solely to copy the camera
    orientation into the cube image, and consumes mouse events that land on the cube.
    """

    action_requested = Signal(str)

    def __init__(
        self,
        render_window: object | None,
        main_renderer: object | None,
        interactor: object | None,
        parent: QWidget,
        *,
        device_pixel_ratio: Callable[[], float] | None = None,
        request_render: Callable[[], object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.parent_widget = parent
        self.render_window = render_window
        self.main_renderer = main_renderer
        self.interactor = interactor
        self._device_pixel_ratio = device_pixel_ratio or (lambda: 1.0)
        self._request_render = request_render
        # Never shown: it paints the image and answers hit tests.
        self.widget = ViewCubeWidget()
        self.widget.action_requested.connect(self.action_requested)
        self._overlay: _CubeImageOverlay | None = None
        self._cube_visible = False
        self._axes_visible = False
        self._closed = False
        self._started = False
        self._observer_id: int | None = None
        self._camera_signature: tuple[float, ...] | None = None
        self._camera_update_count = 0
        self._image_update_count = 0
        self._image_dirty = True
        self._pressed: str | None = None
        self._pointer: QPointF | None = None  # last cursor position, relative to the cube
        self._last_error: str | None = None

    # -- state --------------------------------------------------------------------

    @property
    def visible(self) -> bool:
        """Whether the clickable cube is shown."""

        return self._cube_visible

    @property
    def camera_signature(self) -> tuple[float, ...] | None:
        return self._camera_signature

    @property
    def camera_update_count(self) -> int:
        return self._camera_update_count

    @property
    def image_update_count(self) -> int:
        return self._image_update_count

    @property
    def observer_count(self) -> int:
        return 0 if self._observer_id is None else 1

    @property
    def observer_records(self) -> tuple[tuple[object, int], ...]:
        if self.interactor is None or self._observer_id is None:
            return ()
        return ((self.interactor, self._observer_id),)

    @property
    def overlay_renderer(self) -> object | None:
        return None if self._overlay is None else self._overlay.renderer

    @property
    def overlay_actor(self) -> object | None:
        return None if self._overlay is None else self._overlay.actor

    @property
    def logical_bounds(self) -> tuple[int, int, int, int]:
        """The cube's rectangle in viewport (logical) pixels: x, y, width, height."""

        width = int(self.parent_widget.width())
        x = max(width - CUBE_WIDGET_SIZE - CUBE_MARGIN, 0)
        return (x, CUBE_MARGIN, CUBE_WIDGET_SIZE, CUBE_WIDGET_SIZE)

    # -- lifecycle ----------------------------------------------------------------

    def start(self) -> bool:
        if self._closed:
            return False
        first_start = not self._started
        self._started = True
        if first_start:
            try:
                self._create_overlay()
            except (AttributeError, ImportError, RuntimeError, TypeError, ValueError) as exc:
                self._last_error = f"View cube overlay startup failed: {type(exc).__name__}: {exc}"
                raise
            if self.interactor is not None:
                self._observer_id = int(self.interactor.AddObserver("InteractionEvent", self._on_interaction))
        self.update_layout()
        self.sync_camera(force=first_start)  # start() is called on every scene flush
        return True

    def _create_overlay(self) -> None:
        if self.render_window is None or self.main_renderer is None or self._overlay is not None:
            return
        self._overlay = _CubeImageOverlay(self.render_window, self.main_renderer)
        self._apply_visibility()

    def set_visibility(self, *, gizmo: bool, controls: bool) -> None:
        """``controls`` shows the clickable cube; ``gizmo`` shows the X/Y/Z axis balls."""

        changed = (bool(controls), bool(gizmo)) != (self._cube_visible, self._axes_visible)
        self._cube_visible = bool(controls)
        self._axes_visible = bool(gizmo)
        if changed:
            self.widget.set_parts(cube=self._cube_visible, axes=self._axes_visible)
            self._image_dirty = True
        self._apply_visibility()
        self.update_layout()
        self._refresh_image()

    def set_visible(self, visible: bool) -> None:
        self.set_visibility(gizmo=self._axes_visible, controls=visible)

    def _apply_visibility(self) -> None:
        if self._overlay is not None:
            self._overlay.set_draw(self._cube_visible or self._axes_visible)

    def update_layout(self) -> bool:
        if self._closed or self._overlay is None or self.render_window is None:
            return False
        try:
            width, height = self.render_window.GetSize()
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            self._last_error = f"View cube layout failed: {type(exc).__name__}: {exc}"
            return False
        viewport = normalized_cube_viewport(width, height, self._device_pixel_ratio())
        if viewport is None or viewport == self._current_viewport():
            return False
        self._overlay.set_viewport(viewport)
        self._image_dirty = True
        self._refresh_image()
        return True

    def _current_viewport(self) -> tuple[float, float, float, float] | None:
        if self._overlay is None:
            return None
        return tuple(float(value) for value in self._overlay.renderer.GetViewport())  # type: ignore[return-value]

    def sync_camera(self, *, force: bool = False) -> bool:
        if self._closed or self.main_renderer is None:
            return False
        try:
            camera = self.main_renderer.GetActiveCamera()
            orientation = normalized_camera_orientation(
                camera.GetDirectionOfProjection(), camera.GetViewUp()
            )
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            self._last_error = f"View cube camera sync failed: {type(exc).__name__}: {exc}"
            return False
        if orientation is None:
            return False
        forward, up = orientation
        signature = tuple(round(value, 9) for value in (*forward, *up))
        if not force and signature == self._camera_signature:
            return False
        self._camera_signature = signature
        self._camera_update_count += 1
        self.widget.set_orientation(forward, up)
        if self._pointer is not None:
            # The region under a stationary cursor changes when the cube turns.
            hit = self.widget.hit_at(self._pointer)
            self.widget.set_hover(None if hit is None else hit.hover_key)
        self._image_dirty = True
        self._refresh_image()
        self._last_error = None
        return True

    def _refresh_image(self) -> None:
        """Repaint the cube into the overlay image if anything changed."""

        if self._overlay is None or not self._image_dirty or not (self._cube_visible or self._axes_visible):
            return
        try:
            import numpy as np

            ratio = max(float(self._device_pixel_ratio()), 1.0)
            image = self.widget.render_image(ratio)
            width, height = image.width(), image.height()
            pixels = np.frombuffer(image.constBits(), dtype=np.uint8, count=height * image.bytesPerLine())
            rgba = pixels.reshape(height, image.bytesPerLine())[:, : width * 4].reshape(height, width, 4)
            self._overlay.set_image(rgba, width, height)
        except (AttributeError, ImportError, RuntimeError, TypeError, ValueError) as exc:
            self._last_error = f"View cube image update failed: {type(exc).__name__}: {exc}"
            return
        self._image_dirty = False
        self._image_update_count += 1

    def close(self) -> None:
        if self._closed:
            return
        if self.interactor is not None and self._observer_id is not None:
            try:
                self.interactor.RemoveObserver(self._observer_id)
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                self._last_error = f"View cube observer removal failed: {type(exc).__name__}: {exc}"
            self._observer_id = None
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None
        self.interactor = None
        self.main_renderer = None
        self.render_window = None
        self._closed = True

    def diagnostic_state(self) -> NavigationClusterDiagnosticState:
        return NavigationClusterDiagnosticState(
            cube_visible=self._cube_visible,
            axes_visible=self._axes_visible,
            overlay_attached=self._overlay is not None and self._overlay.attached(),
            overlay_viewport=self._current_viewport(),
            camera_signature=self._camera_signature,
            observer_count=self.observer_count,
            camera_update_count=self._camera_update_count,
            image_update_count=self._image_update_count,
            logical_bounds=self.logical_bounds,
            last_error=self._last_error,
        )

    # -- mouse --------------------------------------------------------------------

    def handle_mouse_event(self, event: QMouseEvent) -> bool:
        """Hover and click handling for events on the viewport; True if consumed."""

        if self._closed or not self._cube_visible:
            return False
        event_type = event.type()
        x, y, _w, _h = self.logical_bounds
        point = event.position()
        local = QPointF(point.x() - x, point.y() - y)
        hit = self.widget.hit_at(local)
        if event_type == QEvent.Type.MouseMove:
            if event.buttons() != Qt.MouseButton.NoButton:
                return False  # a drag elsewhere keeps going; never hijack it
            self._pointer = local
            self._set_hover(None if hit is None else hit.hover_key, None if hit is None else hit.title)
            return False  # let the viewport see idle motion as before
        if event_type == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
            self._pressed = None if hit is None else hit.action_id
            return hit is not None
        if event_type == QEvent.Type.MouseButtonRelease and event.button() == Qt.MouseButton.LeftButton:
            pressed, self._pressed = self._pressed, None
            if pressed is None:
                return False
            if hit is not None and hit.action_id == pressed:
                self.action_requested.emit(pressed)
            return True
        return False

    def leave(self) -> None:
        self._pointer = None
        self._set_hover(None, None)

    def _set_hover(self, key: str | None, title: str | None) -> None:
        if not self.widget.set_hover(key):
            return
        self._image_dirty = True
        self._refresh_image()
        parent = self.parent_widget
        interactor = self.interactor
        for target in (parent, interactor):
            if target is None:
                continue
            try:
                if key is None:
                    target.unsetCursor()
                else:
                    target.setCursor(Qt.CursorShape.PointingHandCursor)
            except (AttributeError, RuntimeError):
                pass
        if interactor is not None and title:
            try:
                interactor.setToolTip(title)
            except (AttributeError, RuntimeError):
                pass
        elif interactor is not None:
            try:
                interactor.setToolTip("")
            except (AttributeError, RuntimeError):
                pass
        if self._request_render is not None:
            try:
                self._request_render()
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass

    def _on_interaction(self, _caller: object, _event: object) -> None:
        self.sync_camera()


def _renderers(render_window: object) -> tuple[object, ...]:
    collection = render_window.GetRenderers()  # type: ignore[attr-defined]
    collection.InitTraversal()
    result: list[object] = []
    while True:
        renderer = collection.GetNextItem()
        if renderer is None:
            break
        result.append(renderer)
    return tuple(result)


__all__ = (
    "NavigationClusterDiagnosticState",
    "ViewportNavigationCluster",
    "normalized_cube_viewport",
)
