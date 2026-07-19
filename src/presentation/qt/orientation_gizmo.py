"""Dedicated screen-space orientation gizmo for the openRetop viewport."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Callable, Iterable


GIZMO_LOGICAL_SIZE = 96
GIZMO_LOGICAL_MARGIN = 12
GIZMO_CONTROL_GAP = 8
_CAMERA_DISTANCE = 4.0
_CAMERA_PARALLEL_SCALE = 0.82


@dataclass(frozen=True, slots=True)
class OrientationGizmoDiagnosticState:
    """Structured state for diagnostics and display-independent tests."""

    enabled: bool
    renderer_attached: bool
    renderer_layer: int | None
    renderer_viewport: tuple[float, float, float, float] | None
    renderer_draw: bool
    renderer_interactive: bool | None
    renderer_transparent: bool
    actor_visible: bool
    actor_pickable: bool | None
    camera_signature: tuple[float, ...] | None
    observer_count: int
    creation_count: int
    renderer_creation_count: int
    actor_creation_count: int
    camera_update_count: int
    layout_update_count: int
    last_error: str | None


class OrientationGizmoController:
    """Own one noninteractive orientation renderer, actor, and observer.

    The existing QVTK render window remains the only native window and the
    existing interactor remains the only input owner.  This controller adds one
    transparent renderer layer and observes native interaction only to mirror
    main-camera orientation into its independent parallel camera.
    """

    def __init__(
        self,
        render_window: object | None,
        main_renderer: object | None,
        interactor: object | None,
        *,
        device_pixel_ratio: Callable[[], float] | None = None,
    ) -> None:
        self.render_window = render_window
        self.main_renderer = main_renderer
        self.interactor = interactor
        self.renderer: object | None = None
        self.actor: object | None = None
        self.enabled = False
        self._attached = False
        self._closed = False
        self._observer_id: int | None = None
        self._camera_signature: tuple[float, ...] | None = None
        self._layout_signature: tuple[float, float, float, float] | None = None
        self._device_pixel_ratio = device_pixel_ratio or (lambda: 1.0)
        self._renderer_creation_count = 0
        self._actor_creation_count = 0
        self._camera_update_count = 0
        self._layout_update_count = 0
        self._last_error: str | None = None

    @property
    def observer_records(self) -> tuple[tuple[object, int], ...]:
        if self.interactor is None or self._observer_id is None:
            return ()
        return ((self.interactor, self._observer_id),)

    @property
    def observer_count(self) -> int:
        return 0 if self._observer_id is None else 1

    @property
    def camera_signature(self) -> tuple[float, ...] | None:
        return self._camera_signature

    @property
    def camera_update_count(self) -> int:
        return self._camera_update_count

    @property
    def logical_size(self) -> int:
        return GIZMO_LOGICAL_SIZE

    @property
    def logical_margin(self) -> int:
        return GIZMO_LOGICAL_MARGIN

    def start(self) -> bool:
        """Create, attach, and observe exactly once."""

        if self._closed:
            return False
        if self._attached and self.renderer is not None and self.actor is not None:
            self._register_observer()
            return True
        if self.render_window is None or self.main_renderer is None:
            return False
        try:
            if self.renderer is None or self.actor is None:
                self._create_renderer_and_actor()
            assert self.renderer is not None
            layer = _available_overlay_layer(self.render_window, self.main_renderer)
            self.renderer.SetLayer(layer)
            current_layers = int(self.render_window.GetNumberOfLayers())
            required_layers = layer + 1
            if current_layers < required_layers:
                self.render_window.SetNumberOfLayers(required_layers)
            if not _renderer_is_attached(self.render_window, self.renderer):
                self.render_window.AddRenderer(self.renderer)
            self._attached = True
            self._register_observer()
            self.update_layout()
            self._apply_visibility()
            if self.enabled:
                self.sync_camera(force=True)
        except (AttributeError, ImportError, RuntimeError, TypeError, ValueError) as exc:
            self._record_error("Orientation gizmo startup failed", exc)
            raise
        self._last_error = None
        return True

    def set_enabled(self, enabled: bool) -> bool:
        requested = bool(enabled)
        changed = requested != self.enabled
        self.enabled = requested
        if self.renderer is not None and self.actor is not None:
            self._apply_visibility()
            if self.enabled:
                self.sync_camera(force=changed)
        return changed

    def update_layout(
        self,
        width: object | None = None,
        height: object | None = None,
        device_pixel_ratio: object | None = None,
    ) -> bool:
        if self.renderer is None or self.render_window is None:
            return False
        try:
            if width is None or height is None:
                width, height = self.render_window.GetSize()
            ratio = (
                self._device_pixel_ratio()
                if device_pixel_ratio is None
                else device_pixel_ratio
            )
            viewport = normalized_gizmo_viewport(width, height, ratio)
            if viewport is None or viewport == self._layout_signature:
                return False
            self.renderer.SetViewport(*viewport)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            self._record_error("Orientation gizmo layout failed", exc)
            return False
        self._layout_signature = viewport
        self._layout_update_count += 1
        self._last_error = None
        return True

    def sync_camera(self, *, force: bool = False) -> bool:
        if (
            not self.enabled
            or self.renderer is None
            or self.main_renderer is None
        ):
            return False
        try:
            source = self.main_renderer.GetActiveCamera()
            orientation = normalized_camera_orientation(
                source.GetDirectionOfProjection(),
                source.GetViewUp(),
            )
            if orientation is None:
                return False
            forward, view_up = orientation
            signature = tuple(
                round(value, 12) for value in (*forward, *view_up)
            )
            if not force and signature == self._camera_signature:
                return False
            camera = self.renderer.GetActiveCamera()
            camera.SetFocalPoint(0.0, 0.0, 0.0)
            camera.SetPosition(
                -forward[0] * _CAMERA_DISTANCE,
                -forward[1] * _CAMERA_DISTANCE,
                -forward[2] * _CAMERA_DISTANCE,
            )
            camera.SetViewUp(*view_up)
            camera.ParallelProjectionOn()
            camera.SetParallelScale(_CAMERA_PARALLEL_SCALE)
            self.renderer.ResetCameraClippingRange()
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            self._record_error("Orientation gizmo camera sync failed", exc)
            return False
        self._camera_signature = signature
        self._camera_update_count += 1
        self._last_error = None
        return True

    def close(self) -> None:
        if self._closed:
            return
        if self.interactor is not None and self._observer_id is not None:
            try:
                self.interactor.RemoveObserver(self._observer_id)
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                self._record_error("Orientation gizmo observer removal failed", exc)
            self._observer_id = None
        if self.renderer is not None:
            try:
                self.renderer.SetDraw(False)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        if self.actor is not None:
            try:
                self.actor.SetVisibility(False)
            except (AttributeError, RuntimeError, TypeError, ValueError):
                pass
        if self.renderer is not None and self.render_window is not None:
            try:
                if not bool(self.render_window.GetNeverRendered()):
                    # Caption and axes props own OpenGL resources. Release them
                    # while QVTK's native context is still valid; retaining a
                    # rendered overlay past Finalize produces late Win32 WGL
                    # cleanup errors.
                    self.renderer.ReleaseGraphicsResources(self.render_window)
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                self._record_error("Orientation gizmo resource release failed", exc)
        if (
            self._attached
            and self.render_window is not None
            and self.renderer is not None
        ):
            try:
                self.render_window.RemoveRenderer(self.renderer)
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                self._record_error("Orientation gizmo detach failed", exc)
        self._attached = False
        self.actor = None
        self.renderer = None
        self.interactor = None
        self.main_renderer = None
        self.render_window = None
        self._closed = True

    def diagnostic_state(self) -> OrientationGizmoDiagnosticState:
        viewport = _renderer_viewport(self.renderer)
        attached = (
            self.renderer is not None
            and self.render_window is not None
            and _renderer_is_attached(self.render_window, self.renderer)
        )
        background_alpha = _call_float(self.renderer, "GetBackgroundAlpha")
        preserve_color = _call_bool(self.renderer, "GetPreserveColorBuffer")
        return OrientationGizmoDiagnosticState(
            enabled=self.enabled,
            renderer_attached=attached,
            renderer_layer=_call_int(self.renderer, "GetLayer"),
            renderer_viewport=viewport,
            renderer_draw=bool(_call_bool(self.renderer, "GetDraw")),
            renderer_interactive=_call_bool(self.renderer, "GetInteractive"),
            renderer_transparent=(
                background_alpha == 0.0 and bool(preserve_color)
            ),
            actor_visible=bool(_call_bool(self.actor, "GetVisibility")),
            actor_pickable=_call_bool(self.actor, "GetPickable"),
            camera_signature=self._camera_signature,
            observer_count=self.observer_count,
            creation_count=max(
                self._renderer_creation_count,
                self._actor_creation_count,
            ),
            renderer_creation_count=self._renderer_creation_count,
            actor_creation_count=self._actor_creation_count,
            camera_update_count=self._camera_update_count,
            layout_update_count=self._layout_update_count,
            last_error=self._last_error,
        )

    def _create_renderer_and_actor(self) -> None:
        from vtkmodules.vtkRenderingAnnotation import vtkAxesActor
        from vtkmodules.vtkRenderingCore import vtkRenderer

        actor = vtkAxesActor()
        actor.SetTotalLength(0.86, 0.86, 0.86)
        actor.SetNormalizedShaftLength(0.72, 0.72, 0.72)
        actor.SetNormalizedTipLength(0.28, 0.28, 0.28)
        actor.SetShaftTypeToCylinder()
        actor.SetTipTypeToCone()
        actor.SetCylinderRadius(0.038)
        actor.SetConeRadius(0.13)
        actor.SetSphereRadius(0.060)
        actor.AxisLabelsOn()
        actor.PickableOff()
        actor.DragableOff()
        _style_axis_caption(actor.GetXAxisCaptionActor2D(), (0.95, 0.25, 0.22))
        _style_axis_caption(actor.GetYAxisCaptionActor2D(), (0.25, 0.92, 0.34))
        _style_axis_caption(actor.GetZAxisCaptionActor2D(), (0.28, 0.55, 1.00))

        renderer = vtkRenderer()
        renderer.InteractiveOff()
        renderer.SetBackground(0.0, 0.0, 0.0)
        renderer.SetBackgroundAlpha(0.0)
        renderer.SetPreserveColorBuffer(True)
        renderer.SetPreserveDepthBuffer(False)
        renderer.EraseOff()
        renderer.SetDraw(False)
        renderer.AddActor(actor)

        self.actor = actor
        self.renderer = renderer
        self._actor_creation_count += 1
        self._renderer_creation_count += 1

    def _register_observer(self) -> None:
        if self.interactor is None or self._observer_id is not None:
            return
        observer_id = self.interactor.AddObserver(
            "InteractionEvent",
            self._on_interaction,
        )
        self._observer_id = int(observer_id)

    def _apply_visibility(self) -> None:
        if self.actor is not None:
            self.actor.SetVisibility(self.enabled)
        if self.renderer is not None:
            self.renderer.SetDraw(self.enabled)

    def _on_interaction(self, _caller: object, _event: object) -> None:
        self.sync_camera()

    def _record_error(self, context: str, exc: Exception) -> None:
        self._last_error = f"{context}: {type(exc).__name__}: {exc}"


def normalized_gizmo_viewport(
    width: object,
    height: object,
    device_pixel_ratio: object = 1.0,
    *,
    logical_size: float = GIZMO_LOGICAL_SIZE,
    logical_margin: float = GIZMO_LOGICAL_MARGIN,
) -> tuple[float, float, float, float] | None:
    """Return a finite top-left normalized viewport with fixed logical size."""

    try:
        pixel_width = float(width)
        pixel_height = float(height)
        ratio = float(device_pixel_ratio)
        size = float(logical_size)
        margin = float(logical_margin)
    except (TypeError, ValueError):
        return None
    if not all(
        math.isfinite(value)
        for value in (pixel_width, pixel_height, ratio, size, margin)
    ):
        return None
    if pixel_width <= 0.0 or pixel_height <= 0.0 or size <= 0.0:
        return None
    if ratio <= 0.0:
        ratio = 1.0
    size_pixels = min(size * ratio, pixel_width, pixel_height)
    margin_pixels = max(margin, 0.0) * ratio
    margin_x = min(margin_pixels, max(pixel_width - size_pixels, 0.0))
    margin_y = min(margin_pixels, max(pixel_height - size_pixels, 0.0))
    x0 = margin_x / pixel_width
    x1 = (margin_x + size_pixels) / pixel_width
    y1 = (pixel_height - margin_y) / pixel_height
    y0 = (pixel_height - margin_y - size_pixels) / pixel_height
    result = (x0, max(y0, 0.0), min(x1, 1.0), min(max(y1, 0.0), 1.0))
    return result if all(math.isfinite(value) for value in result) else None


def normalized_camera_orientation(
    direction: Iterable[object],
    view_up: Iterable[object],
) -> tuple[tuple[float, float, float], tuple[float, float, float]] | None:
    """Return finite forward/up unit vectors with an orthogonal view-up."""

    forward = _unit_vector(direction)
    up = _unit_vector(view_up)
    if forward is None or up is None:
        return None
    projection = _dot(up, forward)
    corrected = _unit_vector(
        tuple(up[index] - projection * forward[index] for index in range(3))
    )
    if corrected is None:
        candidate = min(
            ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)),
            key=lambda axis: abs(_dot(axis, forward)),
        )
        projection = _dot(candidate, forward)
        corrected = _unit_vector(
            tuple(
                candidate[index] - projection * forward[index]
                for index in range(3)
            )
        )
    if corrected is None:
        return None
    return (forward, corrected)


def _style_axis_caption(caption: object, color: tuple[float, float, float]) -> None:
    caption.BorderOff()
    caption.LeaderOff()
    caption.SetPadding(0)
    text = caption.GetCaptionTextProperty()
    text.SetColor(*color)
    text.SetFontSize(14)
    text.BoldOn()
    text.ShadowOff()
    text.SetOpacity(1.0)
    text.SetBackgroundOpacity(0.0)
    caption.GetTextActor().SetTextScaleModeToNone()


def _available_overlay_layer(render_window: object, main_renderer: object) -> int:
    occupied = {
        int(renderer.GetLayer())
        for renderer in _renderers(render_window)
        if renderer is not main_renderer
    }
    layer = 1
    while layer in occupied:
        layer += 1
    return layer


def _renderers(render_window: object) -> tuple[object, ...]:
    collection = render_window.GetRenderers()
    collection.InitTraversal()
    result: list[object] = []
    while True:
        renderer = collection.GetNextItem()
        if renderer is None:
            break
        result.append(renderer)
    return tuple(result)


def _renderer_is_attached(render_window: object, renderer: object) -> bool:
    return any(value is renderer for value in _renderers(render_window))


def _renderer_viewport(
    renderer: object | None,
) -> tuple[float, float, float, float] | None:
    if renderer is None:
        return None
    try:
        values = tuple(float(value) for value in renderer.GetViewport())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None
    return values if len(values) == 4 else None


def _call_bool(value: object | None, method_name: str) -> bool | None:
    result = _call(value, method_name)
    return None if result is None else bool(result)


def _call_int(value: object | None, method_name: str) -> int | None:
    result = _call(value, method_name)
    return None if result is None else int(result)


def _call_float(value: object | None, method_name: str) -> float | None:
    result = _call(value, method_name)
    return None if result is None else float(result)


def _call(value: object | None, method_name: str) -> object | None:
    if value is None:
        return None
    method = getattr(value, method_name, None)
    if not callable(method):
        return None
    try:
        return method()
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return None


def _unit_vector(values: Iterable[object]) -> tuple[float, float, float] | None:
    try:
        result = tuple(float(value) for value in values)
    except (TypeError, ValueError):
        return None
    if len(result) != 3 or not all(math.isfinite(value) for value in result):
        return None
    length = math.sqrt(sum(value * value for value in result))
    if length <= 1e-12:
        return None
    return tuple(value / length for value in result)


def _dot(first: Iterable[float], second: Iterable[float]) -> float:
    return sum(left * right for left, right in zip(first, second))


__all__ = (
    "GIZMO_CONTROL_GAP",
    "GIZMO_LOGICAL_MARGIN",
    "GIZMO_LOGICAL_SIZE",
    "OrientationGizmoController",
    "OrientationGizmoDiagnosticState",
    "normalized_camera_orientation",
    "normalized_gizmo_viewport",
)
