"""Drive the real openRetop window the way a person does: workspace tabs, toolbar and panel
buttons clicked as widgets, real mouse press / move / release events in the 3D view, real
keys. Every step reports what the user would see (status line, tool hint, panel text)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QAbstractButton, QApplication, QToolBar, QToolButton

app = QApplication.instance() or QApplication(sys.argv)

from openretop.bootstrap import create_application  # noqa: E402
from openretop.infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from openretop.presentation.qt.background import ThreadedExecutor  # noqa: E402
from openretop.presentation.qt.main_window import OpenRetopV3Window  # noqa: E402

LOG: list[str] = []


def log(text: str) -> None:
    LOG.append(text)
    print(text, flush=True)


class Human:
    def __init__(self, out: Path, *, threaded: bool = True) -> None:
        self.out = out
        out.mkdir(parents=True, exist_ok=True)
        self.composition = create_application(settings_repository=InMemorySettingsRepository())
        self.window = OpenRetopV3Window(self.composition, executor=ThreadedExecutor() if threaded else None)
        self.window.resize(1440, 900)
        self.window.show()
        self.window.activateWindow()
        self.window.raise_()
        self.wait(600)
        self.window.viewport.start()
        self.wait(300)
        self.shots = 0

    # -- waiting -----------------------------------------------------------------------------

    def wait(self, ms: int = 120) -> None:
        # a real event loop (as app.exec() runs): QTest.qWait starved the worker thread
        from PySide6.QtCore import QEventLoop, QTimer

        loop = QEventLoop()
        QTimer.singleShot(max(1, ms), loop.quit)
        loop.exec()

    def idle(self, timeout: float = 120.0) -> None:
        """Until a background task (load, fit, trim ...) has finished."""

        import time

        start = time.perf_counter()
        executor = self.window._executor
        while executor.busy and time.perf_counter() - start < timeout:
            self.wait(50)
        self.wait(150)

    # -- what the user sees ------------------------------------------------------------------

    def status(self) -> str:
        return self.window.statusBar().currentMessage()

    def hint(self) -> str:
        return self.window.tool_modes.state.instructions if self.window.tool_modes.state.phase not in ("inactive", "finished") else ""

    def say(self, label: str) -> None:
        log(f"  [{label}] status: {self.status()!r}")

    def shot(self, name: str) -> Path:
        self.wait(400)
        self.shots += 1
        path = self.out / f"{self.shots:02d}_{name}.png"
        app.primaryScreen().grabWindow(self.window.winId()).save(str(path))
        from vtkmodules.vtkIOImage import vtkPNGWriter
        from vtkmodules.vtkRenderingCore import vtkWindowToImageFilter

        rw = self.window.viewport.render_window
        rw.Render()
        f = vtkWindowToImageFilter()
        f.SetInput(rw)
        f.ReadFrontBufferOff()
        f.Update()
        w = vtkPNGWriter()
        w.SetFileName(str(path.with_name(path.stem + "_view.png")))
        w.SetInputConnection(f.GetOutputPort())
        w.Write()
        return path

    # -- widgets -----------------------------------------------------------------------------

    def tab(self, title: str) -> None:
        tabs = self.window.workspace_tabs
        index = next(i for i in range(tabs.count()) if tabs.tabText(i) == title)
        QTest.mouseClick(tabs, Qt.LeftButton, Qt.NoModifier, tabs.tabRect(index).center())
        self.wait()

    def toolbar_button(self, label: str) -> QToolButton | None:
        for bar in self.window.findChildren(QToolBar):
            if not bar.isVisible():
                continue
            for action in bar.actions():
                if action.text().replace("&", "") == label or action.iconText() == label:
                    widget = bar.widgetForAction(action)
                    if widget is not None and widget.isVisible():
                        return widget  # type: ignore[return-value]
        return None

    def click_toolbar(self, label: str) -> bool:
        button = self.toolbar_button(label)
        if button is None:
            log(f"  !! no visible toolbar button {label!r}")
            return False
        if not button.isEnabled():
            log(f"  !! toolbar button {label!r} is disabled: {button.toolTip()[:120]!r}")
            return False
        QTest.mouseClick(button, Qt.LeftButton)
        self.wait()
        self.idle()
        return True

    def panel_button(self, text: str) -> QAbstractButton | None:
        panel = self.window.surfacing_panel
        for button in panel.findChildren(QAbstractButton):
            if button.text() == text and button.isVisible():
                return button
        return None

    def click_panel(self, text: str) -> bool:
        button = self.panel_button(text)
        if button is None:
            log(f"  !! no visible panel button {text!r}")
            return False
        if not button.isEnabled():
            log(f"  !! panel button {text!r} is disabled")
            return False
        QTest.mouseClick(button, Qt.LeftButton)
        self.wait()
        self.idle()
        return True

    # -- the 3D view -------------------------------------------------------------------------

    @property
    def view(self):
        return self.window.viewport.interactor

    def screen_of(self, world: object) -> tuple[int, int] | None:
        """Qt widget coordinates of a world point (None if off screen)."""

        projected = np.asarray(self.window.viewport.project_points(np.asarray(world, dtype=float).reshape(1, 3)), dtype=float).reshape(-1)
        if projected.size < 2 or not np.all(np.isfinite(projected[:2])):
            return None
        height = self.view.height()
        x, y = int(round(projected[0])), int(round(height - 1 - projected[1]))
        if not (0 <= x < self.view.width() and 0 <= y < height):
            return None
        return x, y

    def _send(self, kind: QEvent.Type, x: float, y: float, button: Qt.MouseButton, buttons: Qt.MouseButton, modifiers=Qt.NoModifier) -> None:
        point = QPointF(x, y)
        global_point = QPointF(self.view.mapToGlobal(QPoint(int(x), int(y))))
        event = QMouseEvent(kind, point, global_point, button, buttons, modifiers)
        QApplication.sendEvent(self.view, event)

    def move(self, x: float, y: float) -> None:
        self._send(QEvent.MouseMove, x, y, Qt.NoButton, Qt.NoButton)
        self.wait(30)

    def click(self, x: float, y: float, modifiers=Qt.NoModifier) -> None:
        self.move(x, y)
        self._send(QEvent.MouseButtonPress, x, y, Qt.LeftButton, Qt.LeftButton, modifiers)
        self.wait(30)
        self._send(QEvent.MouseButtonRelease, x, y, Qt.LeftButton, Qt.NoButton, modifiers)
        self.wait(150)
        self.idle()

    def click_world(self, world: object, modifiers=Qt.NoModifier) -> bool:
        spot = self.screen_of(world)
        if spot is None:
            log(f"  !! {np.round(world, 2).tolist()} is off screen")
            return False
        self.click(*spot, modifiers=modifiers)
        return True

    def drag(self, start: tuple[float, float], end: tuple[float, float], steps: int = 8) -> None:
        self.move(*start)
        self._send(QEvent.MouseButtonPress, start[0], start[1], Qt.LeftButton, Qt.LeftButton)
        self.wait(30)
        for t in np.linspace(0, 1, steps + 1)[1:]:
            x = start[0] + (end[0] - start[0]) * t
            y = start[1] + (end[1] - start[1]) * t
            self._send(QEvent.MouseMove, x, y, Qt.NoButton, Qt.LeftButton)
            self.wait(30)
        self._send(QEvent.MouseButtonRelease, end[0], end[1], Qt.LeftButton, Qt.NoButton)
        self.wait(200)
        self.idle()

    def key(self, key: Qt.Key, text: str = "", modifiers=Qt.NoModifier) -> None:
        self.view.setFocus()
        for kind in (QEvent.KeyPress, QEvent.KeyRelease):
            QApplication.sendEvent(self.view, QKeyEvent(kind, key, modifiers, text))
        self.wait(150)
        self.idle()

    def close(self) -> None:
        self.window.set_project_dirty(False)
        self.window.close()


def scan_of(part: str) -> Path:
    """A generated scan as an STL file (as a user would open one)."""

    import trimesh

    from openretop.benchmarks import make_part, scan_from_part

    path = Path(os.environ["TEMP"]) / f"human_{part}.stl"
    if not path.exists():
        scan = scan_from_part(make_part(part), noise_sigma=0.02, seed=1, edge_length=0.8)
        trimesh.Trimesh(np.asarray(scan.vertices), np.asarray(scan.triangles)).export(path)
    return path


# -- dialogs, files and other mouse buttons ------------------------------------------------------

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox  # noqa: E402

DIALOGS: list[str] = []


def answer_dialog(*, choice: str | None = None, button: str | None = None, delay: int = 250) -> None:
    """Answer the next modal dialog as a person would: pick ``choice`` in a list, click
    ``button`` (by its text), or OK."""

    def handle() -> None:
        dialog = QApplication.activeModalWidget()
        if dialog is None:
            QTimer.singleShot(100, handle)
            return
        title = dialog.windowTitle()
        if isinstance(dialog, QInputDialog):
            DIALOGS.append(f"input dialog {title!r}: {dialog.labelText()!r} items={dialog.comboBoxItems()[:6]}")
            if choice is not None:
                matches = [item for item in dialog.comboBoxItems() if choice in item]
                if matches:
                    dialog.setTextValue(matches[0])
                else:
                    dialog.setTextValue(choice)
            dialog.accept()
        elif isinstance(dialog, QMessageBox):
            texts = [b.text().replace("&", "") for b in dialog.buttons()]
            DIALOGS.append(f"message box {title!r}: {dialog.text()!r} buttons={texts}")
            target = next((b for b in dialog.buttons() if button and b.text().replace("&", "") == button), None)
            (target or dialog.defaultButton() or dialog.buttons()[0]).click()
        elif isinstance(dialog, QDialog):
            DIALOGS.append(f"dialog {title!r}")
            dialog.accept()
        log(f"  (dialog) {DIALOGS[-1]}")

    QTimer.singleShot(delay, handle)


def stand_in_file_dialogs(open_path: object = None, save_path: object = None) -> None:
    """Windows shows its own file dialogs (not scriptable): answer them with these paths."""

    def get_open(*args, **kwargs):
        log(f"  (file dialog) open {args[1] if len(args) > 1 else ''!r} -> {open_path}")
        return (str(open_path), "") if open_path else ("", "")

    def get_save(*args, **kwargs):
        log(f"  (file dialog) save {args[1] if len(args) > 1 else ''!r} filter {args[3] if len(args) > 3 else ''!r} -> {save_path}")
        return (str(save_path), "") if save_path else ("", "")

    QFileDialog.getOpenFileName = staticmethod(get_open)  # type: ignore[method-assign]
    QFileDialog.getSaveFileName = staticmethod(get_save)  # type: ignore[method-assign]


def button_drag(h: Human, button: Qt.MouseButton, start: tuple[float, float], end: tuple[float, float], modifiers=Qt.NoModifier, steps: int = 10) -> None:
    h.move(*start)
    h._send(QEvent.MouseButtonPress, start[0], start[1], button, button, modifiers)
    h.wait(30)
    for t in np.linspace(0, 1, steps + 1)[1:]:
        h._send(QEvent.MouseMove, start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t, Qt.NoButton, button, modifiers)
        h.wait(25)
    h._send(QEvent.MouseButtonRelease, end[0], end[1], button, Qt.NoButton, modifiers)
    h.wait(200)


def wheel(h: Human, x: float, y: float, notches: int) -> None:
    for _ in range(abs(notches)):
        point = QPointF(x, y)
        event = QWheelEvent(point, QPointF(h.view.mapToGlobal(QPoint(int(x), int(y)))), QPoint(), QPoint(0, 120 if notches > 0 else -120), Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
        QApplication.sendEvent(h.view, event)
        h.wait(40)


def camera(h: Human) -> tuple:
    cam = h.window.viewport.renderer.GetActiveCamera()
    return tuple(round(v, 2) for v in (*cam.GetPosition(), *cam.GetFocalPoint(), cam.GetParallelScale()))
