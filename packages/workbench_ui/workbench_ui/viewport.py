"""Optional VTK Qt host with an explicit, headless-safe lifecycle."""

from __future__ import annotations

import logging
import os

from PySide6.QtCore import Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QFrame, QVBoxLayout, QWidget


_LOG = logging.getLogger(__name__)
_VTK_IMPORT_ERROR: str | None = None
_FREETYPE_AVAILABLE = False

# VTK's modular Python packages do not register implementation factories merely
# by importing vtkRenderingCore.  These imports must precede construction of the
# QVTK widget so vtkRenderWindow resolves to the platform OpenGL implementation.
try:
    import vtkmodules.vtkRenderingOpenGL2  # noqa: F401
    import vtkmodules.vtkInteractionStyle  # noqa: F401

    try:
        import vtkmodules.vtkRenderingFreeType  # noqa: F401
    except ImportError:
        # FreeType is optional in custom VTK builds.  Text actors are unavailable
        # in that case, but the OpenGL viewport itself remains usable.
        pass
    else:
        _FREETYPE_AVAILABLE = True

    from vtkmodules.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor
    from vtkmodules.vtkInteractionStyle import vtkInteractorStyleTrackballCamera
    from vtkmodules.vtkRenderingCore import vtkRenderer
except ImportError as exc:
    QVTKRenderWindowInteractor = None  # type: ignore[assignment]
    vtkInteractorStyleTrackballCamera = None  # type: ignore[assignment]
    vtkRenderer = None  # type: ignore[assignment]
    _VTK_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"


class VTKViewportWidget(QFrame):
    """Embed QVTK without owning application scene policy.

    ``start()`` is the sole native initialization path.  Hosts place and show
    the widget first, call ``start()`` once, and react to ``ready``.  Repeated
    calls are harmless and never recreate VTK objects or initialize twice.
    """

    ready = Signal()
    initialization_failed = Signal(str)
    render_failed = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.renderer = None
        self.render_window = None
        self.interactor = None
        self.interactor_style = None
        self._is_ready = False
        self._start_attempted = False
        self._closing = False
        self._finalized = False
        self._initialization_count = 0
        self._offscreen_start_suppressed = False
        self._last_error: str | None = None
        self._fallback_error: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if _VTK_IMPORT_ERROR is not None:
            self._install_fallback(layout, _VTK_IMPORT_ERROR)
            return

        try:
            assert QVTKRenderWindowInteractor is not None
            assert vtkRenderer is not None
            interactor = QVTKRenderWindowInteractor(self)
            render_window = interactor.GetRenderWindow()
            class_name = _vtk_class_name(render_window)
            if class_name == "vtkRenderWindow":
                raise RuntimeError(
                    "VTK did not register a concrete OpenGL render-window backend."
                )
            renderer = vtkRenderer()
            render_window.AddRenderer(renderer)
            # QVTK defaults to vtkInteractorStyleSwitch, whose active mode is
            # process/input-history dependent.  The reusable host guarantees a
            # concrete CAD-style camera contract; application-specific tools
            # decide which Qt gestures are allowed to reach it.
            assert vtkInteractorStyleTrackballCamera is not None
            interactor_style = vtkInteractorStyleTrackballCamera()
            interactor.SetInteractorStyle(interactor_style)
        except (AttributeError, ImportError, RuntimeError, TypeError, ValueError) as exc:
            _LOG.exception("VTK viewport construction failed")
            self._install_fallback(layout, f"{type(exc).__name__}: {exc}")
            return

        self.interactor = interactor
        self.interactor_style = interactor_style
        self.render_window = render_window
        self.renderer = renderer
        layout.addWidget(interactor)

    @property
    def available(self) -> bool:
        return (
            self.renderer is not None
            and self.render_window is not None
            and self.interactor is not None
        )

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def initialization_count(self) -> int:
        return self._initialization_count

    @property
    def last_error(self) -> str | None:
        return self._last_error or self._fallback_error

    @property
    def freetype_available(self) -> bool:
        return _FREETYPE_AVAILABLE

    def start(self) -> bool:
        """Initialize the embedded VTK interactor exactly once.

        The public QVTK example for VTK 9.6 initializes after the widget is
        shown.  A hidden visible-platform widget is therefore deferred rather
        than initialized against a surface that has not been exposed.  Native
        initialization and rendering are both suppressed on Qt's offscreen
        platform because Win32 cannot provide that plugin a valid pixel format.
        """

        if self._is_ready:
            return True
        if self._closing or not self.available:
            return False
        if _qt_offscreen():
            # vtkWin32OpenGLRenderWindow cannot acquire a valid pixel format
            # from Qt's offscreen platform.  Initializing it can hang before a
            # Python exception is possible, so CI keeps the native path inert.
            self._offscreen_start_suppressed = True
            return False
        assert self.interactor is not None
        if not self.interactor.isVisible():
            self._last_error = "VTK viewport start deferred until the Qt widget is visible."
            return False
        if self._start_attempted:
            return False

        self._start_attempted = True
        try:
            self.interactor.Initialize()
            self.interactor.Start()
            get_initialized = getattr(self.interactor, "GetInitialized", None)
            if callable(get_initialized) and not bool(get_initialized()):
                raise RuntimeError("VTK interactor did not report initialized state.")
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            self._record_failure(
                "VTK viewport initialization failed",
                exc,
                self.initialization_failed,
            )
            return False

        self._initialization_count += 1
        self._last_error = None
        self._is_ready = True
        self.ready.emit()
        return True

    def render(self) -> bool:
        """Render once when native VTK is ready; otherwise return safely."""

        if self._closing or not self._is_ready or self.render_window is None:
            return False
        if _qt_offscreen():
            return False
        try:
            self.render_window.Render()
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            self._record_failure("VTK viewport render failed", exc, self.render_failed)
            return False
        self._last_error = None
        return True

    def diagnostic_state(self) -> dict[str, object]:
        """Return toolkit-level state without triggering rendering."""

        initialized = None
        if self.interactor is not None:
            get_initialized = getattr(self.interactor, "GetInitialized", None)
            if callable(get_initialized):
                try:
                    initialized = bool(get_initialized())
                except (RuntimeError, TypeError, ValueError):
                    initialized = None
        return {
            "available": self.available,
            "ready": self._is_ready,
            "render_window_class": _vtk_class_name(self.render_window),
            "renderer_class": _vtk_class_name(self.renderer),
            "interactor_class": _vtk_class_name(self.interactor),
            "interactor_style_class": _vtk_class_name(self.interactor_style),
            "interactor_initialized": initialized,
            "renderer_size": _vtk_size(self.renderer),
            "render_window_size": _vtk_size(self.render_window),
            "renderer_count": _renderer_count(self.render_window),
            "initialization_count": self._initialization_count,
            "freetype_available": _FREETYPE_AVAILABLE,
            "last_error": self.last_error,
            "offscreen": _qt_offscreen(),
            "offscreen_start_suppressed": self._offscreen_start_suppressed,
        }

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        self._closing = True
        self._is_ready = False
        if self.interactor is not None and not self._finalized:
            try:
                # QVTK's public close path calls Finalize.  The host owns the
                # child and invokes it explicitly while the native surface is
                # still valid, avoiding late Win32 WGL cleanup at GC time.
                self.interactor.Finalize()
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                self._last_error = (
                    "VTK viewport finalization failed: "
                    f"{type(exc).__name__}: {exc}"
                )
                _LOG.exception("VTK viewport finalization failed")
            self._finalized = True
        super().closeEvent(event)

    def _install_fallback(self, layout: QVBoxLayout, error: str) -> None:
        self._fallback_error = str(error)
        label = QLabel(f"VTK viewport unavailable:\n{error}", self)
        label.setWordWrap(True)
        layout.addWidget(label)

    def _record_failure(self, context: str, exc: Exception, signal: Signal) -> None:
        message = f"{context}: {type(exc).__name__}: {exc}"
        self._last_error = message
        _LOG.exception(context)
        signal.emit(message)


def _qt_offscreen() -> bool:
    return os.environ.get("QT_QPA_PLATFORM", "").strip().lower() == "offscreen"


def _vtk_class_name(value: object | None) -> str | None:
    if value is None:
        return None
    get_class_name = getattr(value, "GetClassName", None)
    if callable(get_class_name):
        try:
            return str(get_class_name())
        except (RuntimeError, TypeError, ValueError):
            pass
    return type(value).__name__


def _vtk_size(value: object | None) -> tuple[int, int] | None:
    if value is None:
        return None
    get_size = getattr(value, "GetSize", None)
    if not callable(get_size):
        return None
    try:
        width, height = get_size()
        return (int(width), int(height))
    except (RuntimeError, TypeError, ValueError):
        return None


def _renderer_count(render_window: object | None) -> int:
    if render_window is None:
        return 0
    try:
        return int(render_window.GetRenderers().GetNumberOfItems())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return 0


__all__ = ("VTKViewportWidget",)
