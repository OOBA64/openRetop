"""Standalone Qt/VTK viewport diagnostic for openRetop development.

The normal visible mode opens a temporary window and renders one sphere.  The
``--offscreen`` mode constructs and initializes the same host without issuing
an unsafe visible render.  Neither mode reads or writes application settings or
project files.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import platform
import sys
import traceback


ROOT = Path(__file__).resolve().parents[1]
WORKBENCH_ROOT = ROOT / "packages" / "workbench_ui"


def add_diagnostic_sphere(renderer: object) -> object:
    """Add the script's temporary synthetic actor and return it."""

    from vtkmodules.vtkFiltersSources import vtkSphereSource
    from vtkmodules.vtkRenderingCore import vtkActor, vtkPolyDataMapper

    source = vtkSphereSource()
    source.SetThetaResolution(32)
    source.SetPhiResolution(24)
    mapper = vtkPolyDataMapper()
    mapper.SetInputConnection(source.GetOutputPort())
    actor = vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(1.0, 0.42, 0.08)
    renderer.AddActor(actor)
    return actor


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--offscreen",
        action="store_true",
        help="Use Qt's offscreen platform and suppress the visible Render call.",
    )
    parser.add_argument(
        "--duration-ms",
        type=int,
        default=1500,
        help="Visible smoke-test duration before automatic exit (default: 1500).",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.offscreen:
        # Process-local diagnostic selection; production viewport code never
        # mutates QT_QPA_PLATFORM.
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    for path in (ROOT / "src", WORKBENCH_ROOT):
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))

    print(f"python_executable={sys.executable}")
    print(f"python_version={platform.python_version()}")
    print(f"platform={platform.platform()}")
    print(f"qt_platform={os.environ.get('QT_QPA_PLATFORM', '<default>')}")

    import PySide6
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget
    from vtkmodules.vtkCommonCore import vtkVersion

    backend_imported = _try_import("vtkmodules.vtkRenderingOpenGL2")
    interaction_imported = _try_import("vtkmodules.vtkInteractionStyle")
    freetype_imported = _try_import("vtkmodules.vtkRenderingFreeType")
    try:
        from vtkmodules.qt.QVTKRenderWindowInteractor import (
            QVTKRenderWindowInteractor,
        )
    except ImportError:
        qvtk_available = False
        qvtk_class = None
    else:
        qvtk_available = True
        qvtk_class = QVTKRenderWindowInteractor.__name__

    import workbench_ui.viewport as viewport_module
    from workbench_ui.viewport import VTKViewportWidget

    print(f"pyside6_version={PySide6.__version__}")
    print(f"vtk_version={vtkVersion.GetVTKVersion()}")
    print(f"workbench_viewport_path={Path(viewport_module.__file__).resolve()}")
    print(f"qvtk_available={qvtk_available}")
    print(f"qvtk_class={qvtk_class}")
    print(f"opengl_backend_imported={backend_imported}")
    print(f"interaction_style_imported={interaction_imported}")
    print(f"freetype_imported={freetype_imported}")

    app = QApplication.instance() or QApplication(["diagnose_vtk_viewport"])
    host = QWidget()
    host.setWindowTitle("openRetop VTK viewport diagnostic")
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    viewport = VTKViewportWidget(host)
    layout.addWidget(viewport)
    host.resize(900, 620)

    failures: list[str] = []
    viewport.initialization_failed.connect(failures.append)
    viewport.render_failed.connect(failures.append)
    if not args.offscreen:
        host.show()

    started = viewport.start()
    actor_added = False
    render_completed = False
    if viewport.renderer is not None:
        add_diagnostic_sphere(viewport.renderer)
        actor_added = True
        viewport.renderer.SetBackground(0.062745, 0.074510, 0.086275)
        viewport.renderer.ResetCamera()
    if started:
        render_completed = viewport.render()

    def report() -> None:
        state = viewport.diagnostic_state()
        renderer = viewport.renderer
        render_window = viewport.render_window
        actor_count = _collection_count(renderer, "GetActors")
        camera = None if renderer is None else renderer.GetActiveCamera()
        supports_opengl: object = "not-probed-offscreen"
        opengl_message: object = "not-probed-offscreen"
        if not args.offscreen and render_window is not None:
            # VTK 9.6.2's SupportsOpenGL() probe perturbs the Win32 context and
            # emits wglMakeCurrent errors during otherwise clean teardown.  A
            # completed render on the concrete OpenGL window is direct evidence
            # without changing context ownership.
            supports_opengl = render_completed and "OpenGL" in str(
                state["render_window_class"]
            )
            opengl_message = "successful visible Render() on concrete OpenGL window"

        print(f"viewport_available={state['available']}")
        print(f"viewport_ready={state['ready']}")
        print(f"render_window_class={state['render_window_class']}")
        print(f"renderer_class={state['renderer_class']}")
        print(f"interactor_class={state['interactor_class']}")
        print(f"interactor_style_class={state['interactor_style_class']}")
        print(f"interactor_initialized={state['interactor_initialized']}")
        print(f"offscreen_start_suppressed={state['offscreen_start_suppressed']}")
        print(f"renderer_count={state['renderer_count']}")
        print(f"renderer_size={state['renderer_size']}")
        print(f"render_window_size={state['render_window_size']}")
        print(f"actor_count={actor_count}")
        print(f"synthetic_actor_added={actor_added}")
        print(f"render_completed={render_completed}")
        print(f"supports_opengl={supports_opengl}")
        print(f"opengl_support_message={opengl_message}")
        print(f"camera_position={_call(camera, 'GetPosition')}")
        print(f"camera_focal_point={_call(camera, 'GetFocalPoint')}")
        print(f"camera_clipping_range={_call(camera, 'GetClippingRange')}")
        print(f"camera_view_angle={_call(camera, 'GetViewAngle')}")
        print(f"last_error={state['last_error']}")
        print(f"captured_failures={failures}")
        viewport.close()
        app.quit()

    if args.offscreen:
        report()
        return 0 if viewport.available and actor_added and not started and not failures else 1

    QTimer.singleShot(max(int(args.duration_ms), 100), report)
    result = int(app.exec())
    return result if result else (0 if started and actor_added and render_completed and not failures else 1)


def _try_import(module_name: str) -> bool:
    try:
        __import__(module_name)
    except ImportError:
        return False
    return True


def _collection_count(owner: object | None, getter_name: str) -> int:
    if owner is None:
        return 0
    try:
        return int(getattr(owner, getter_name)().GetNumberOfItems())
    except (AttributeError, RuntimeError, TypeError, ValueError):
        return 0


def _call(owner: object | None, method_name: str) -> object:
    if owner is None:
        return None
    try:
        return getattr(owner, method_name)()
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
        return f"{type(exc).__name__}: {exc}"


def main() -> int:
    try:
        return run()
    except Exception:
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
