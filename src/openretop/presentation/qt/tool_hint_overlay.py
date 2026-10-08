"""The active tool's instructions as a floating pill at the bottom of the viewport.

Painted by Qt into an image and shown by an overlay renderer in the VTK frame (a Qt widget
cannot be drawn over the native OpenGL window), like the view cube.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainter, QPainterPath, QPen

from openretop.presentation.qt.overlay_layers import ImageOverlay

BOTTOM_MARGIN = 18  # logical px between the pill and the bottom of the view
PADDING_X = 14
PADDING_Y = 7
MAX_WIDTH_FRACTION = 0.9  # long hints wrap instead of running off the view
BACKGROUND = QColor(22, 25, 30, 225)
BORDER = QColor(255, 255, 255, 34)
TEXT = QColor(228, 231, 235)


def paint_hint(text: str, ratio: float, max_width: float) -> QImage:
    """The pill as an image in device pixels (``ratio`` device pixels per logical pixel)."""

    font = QFont()
    font.setPointSizeF(9.5)
    font.setWeight(QFont.Weight.Medium)
    metrics = QFontMetricsF(font)
    wrap_width = max(120.0, max_width - 2 * PADDING_X)
    bounds = metrics.boundingRect(QRectF(0, 0, wrap_width, 10_000), int(Qt.TextFlag.TextWordWrap), text)
    width = bounds.width() + 2 * PADDING_X
    height = bounds.height() + 2 * PADDING_Y
    image = QImage(max(1, round(width * ratio)), max(1, round(height * ratio)), QImage.Format.Format_RGBA8888)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.scale(ratio, ratio)
    pill = QPainterPath()
    radius = min(height / 2.0, 14.0)
    pill.addRoundedRect(QRectF(0.5, 0.5, width - 1.0, height - 1.0), radius, radius)
    painter.fillPath(pill, BACKGROUND)
    painter.setPen(QPen(BORDER, 1.0))
    painter.drawPath(pill)
    painter.setFont(font)
    painter.setPen(TEXT)
    painter.drawText(
        QRectF(PADDING_X, PADDING_Y, bounds.width() + 1.0, bounds.height()),
        int(Qt.AlignmentFlag.AlignHCenter | Qt.TextFlag.TextWordWrap),
        text,
    )
    painter.end()
    return image


class ToolHintOverlay:
    """Shows one line of instructions while a tool is active; draws nothing otherwise."""

    def __init__(
        self,
        render_window: object | None,
        main_renderer: object | None,
        *,
        device_pixel_ratio: Callable[[], float] | None = None,
    ) -> None:
        self.render_window = render_window
        self.main_renderer = main_renderer
        self._ratio = device_pixel_ratio or (lambda: 1.0)
        self._overlay: ImageOverlay | None = None
        self.text = ""
        self._image_size: tuple[int, int] = (0, 0)
        self._painted_for: tuple[str, float, int] | None = None
        self._observer: int | None = None
        self._closed = False

    @property
    def visible(self) -> bool:
        return bool(self.text) and self._overlay is not None and bool(self._overlay.renderer.GetDraw())

    @property
    def renderer(self) -> object | None:
        return None if self._overlay is None else self._overlay.renderer

    @property
    def actor(self) -> object | None:
        return None if self._overlay is None else self._overlay.actor

    def set_text(self, text: str) -> None:
        self.text = " ".join(str(text or "").split())
        if self._closed or self.render_window is None or self.main_renderer is None:
            return
        if not self.text:
            if self._overlay is not None:
                self._overlay.set_draw(False)
            return
        self._ensure_overlay()
        assert self._overlay is not None
        self._overlay.set_draw(True)
        self._layout()  # or, before the first frame, on the render window's StartEvent

    def _ensure_overlay(self) -> None:
        if self._overlay is not None:
            return
        self._overlay = ImageOverlay(self.render_window, self.main_renderer)
        # keep the pill centred when the window is resized
        self._observer = self.render_window.AddObserver("StartEvent", lambda *_: self._layout())  # type: ignore[union-attr, attr-defined]

    def _layout(self) -> None:
        overlay = self._overlay
        if overlay is None or not self.text or self.render_window is None:
            return
        width, height = (int(value) for value in self.render_window.GetSize())  # type: ignore[attr-defined]
        if width <= 0 or height <= 0:
            return
        ratio = float(self._ratio() or 1.0)
        key = (self.text, ratio, width)
        if key != self._painted_for:
            image = paint_hint(self.text, ratio, (width / ratio) * MAX_WIDTH_FRACTION)
            pixels = image.constBits()
            import numpy as np

            rgba = np.frombuffer(pixels, dtype=np.uint8, count=image.sizeInBytes()).reshape(
                image.height(), image.bytesPerLine()
            )[:, : image.width() * 4].reshape(image.height(), image.width(), 4)
            overlay.set_image(rgba, image.width(), image.height())
            self._image_size = (image.width(), image.height())
            self._painted_for = key
        image_width, image_height = self._image_size
        left = float(max((width - image_width) // 2, 0))  # whole pixels keep the text crisp
        bottom = float(round(BOTTOM_MARGIN * ratio))
        overlay.set_viewport(
            (
                left / width,
                min(bottom / height, 1.0),
                min((left + image_width) / width, 1.0),
                min((bottom + image_height) / height, 1.0),
            )
        )
        overlay.set_draw(True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._observer is not None and self.render_window is not None:
            try:
                self.render_window.RemoveObserver(self._observer)  # type: ignore[attr-defined]
            except (AttributeError, RuntimeError, TypeError):
                pass
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None


__all__ = ("ToolHintOverlay", "paint_hint")
