from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

import trimesh

ROOT = Path(__file__).resolve().parents[1]

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtGui import QCloseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from openretop.bootstrap import create_application  # noqa: E402
from openretop.infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from openretop.presentation.qt.background import InlineExecutor, ThreadedExecutor  # noqa: E402
from openretop.presentation.qt.main_window import OpenRetopV3Window  # noqa: E402


def pump(condition, timeout: float = 20.0) -> bool:
    """Run the Qt event loop until ``condition()`` holds."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        QApplication.processEvents()
        if condition():
            return True
        time.sleep(0.005)
    return False


class ExecutorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_work_runs_off_thread_and_callback_returns_to_the_ui_thread(self) -> None:
        executor = ThreadedExecutor()
        seen: dict[str, object] = {}

        def work() -> int:
            seen["work_thread"] = threading.current_thread()
            return 42

        def done(value: object) -> None:
            seen["callback_thread"] = threading.current_thread()
            seen["value"] = value

        self.assertTrue(executor.submit("job", work, done, lambda exc: seen.setdefault("error", exc)))
        self.assertTrue(executor.busy)
        self.assertEqual(executor.label, "job")
        self.assertTrue(pump(lambda: "value" in seen))
        self.assertEqual(seen["value"], 42)
        self.assertIsNot(seen["work_thread"], threading.main_thread())
        self.assertIs(seen["callback_thread"], threading.main_thread())
        self.assertFalse(executor.busy)

    def test_errors_are_delivered_to_the_error_callback(self) -> None:
        executor = ThreadedExecutor()
        seen: list[BaseException] = []

        def boom() -> None:
            raise ValueError("bad mesh")

        executor.submit("job", boom, lambda _v: seen.append(RuntimeError("no")), seen.append)
        self.assertTrue(pump(lambda: bool(seen)))
        self.assertIsInstance(seen[0], ValueError)
        self.assertFalse(executor.busy)

    def test_system_exit_in_work_does_not_escape_the_worker(self) -> None:
        executor = ThreadedExecutor()
        seen: list[BaseException] = []

        def exits() -> None:
            raise SystemExit("library tried to quit")

        executor.submit("job", exits, lambda _v: None, seen.append)
        self.assertTrue(pump(lambda: bool(seen)))
        self.assertIsInstance(seen[0], SystemExit)

    def test_second_submit_is_rejected_while_busy(self) -> None:
        executor = ThreadedExecutor()
        release = threading.Event()
        finished: list[object] = []
        self.assertTrue(executor.submit("slow", release.wait, finished.append, finished.append))
        self.assertFalse(executor.submit("other", lambda: 1, finished.append, finished.append))
        release.set()
        self.assertTrue(pump(lambda: len(finished) == 1))
        self.assertTrue(executor.submit("again", lambda: 2, finished.append, finished.append))
        self.assertTrue(pump(lambda: len(finished) == 2))

    def test_event_loop_keeps_running_while_work_is_in_progress(self) -> None:
        executor = ThreadedExecutor()
        ticks: list[int] = []
        timer = QTimer()
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start(10)
        finished: list[object] = []
        executor.submit("slow", lambda: time.sleep(0.4), finished.append, finished.append)
        self.assertTrue(pump(lambda: bool(finished)))
        timer.stop()
        self.assertGreater(len(ticks), 10, "UI thread should have kept processing timers")

    def test_inline_executor_is_synchronous(self) -> None:
        executor = InlineExecutor()
        results: list[object] = []
        self.assertTrue(executor.submit("job", lambda: 7, results.append, results.append))
        self.assertEqual(results, [7])
        executor.submit("job", lambda: 1 / 0, results.append, results.append)
        self.assertIsInstance(results[1], ZeroDivisionError)


class WindowBackgroundTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self) -> OpenRetopV3Window:
        window = OpenRetopV3Window(
            create_application(settings_repository=InMemorySettingsRepository()),
            executor=ThreadedExecutor(),
        )
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window._report_error = lambda title, message: self.errors.append((title, message))  # type: ignore[method-assign]
        return window

    def setUp(self) -> None:
        self.errors: list[tuple[str, str]] = []

    def _open(self, window: OpenRetopV3Window, directory: str):
        path = Path(directory) / "part.stl"
        trimesh.creation.icosphere(subdivisions=3, radius=10.0).export(path)
        self.assertTrue(window.open_model_path(path, units="mm"))
        # Loading is asynchronous: nothing is installed until the worker finishes.
        self.assertIsNone(window.composition.state.mesh_object)
        self.assertTrue(pump(lambda: window.composition.state.mesh_object is not None))
        return path

    def test_model_import_runs_in_the_background(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            self._open(window, directory)
        self.assertEqual(window.composition.state.units, "mm")
        self.assertFalse(window._executor.busy)
        self.assertEqual(self.errors, [])

    def test_failed_import_keeps_the_current_model_and_reports(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            self._open(window, directory)
            previous = window.composition.state.mesh_object
            broken = Path(directory) / "broken.stl"
            broken.write_bytes(b"solid x\nnope\n")
            self.assertTrue(window.open_model_path(broken, units="mm"))
            self.assertTrue(pump(lambda: bool(self.errors)))
        self.assertIs(window.composition.state.mesh_object, previous)
        self.assertEqual(self.errors[0][0], "Model import failed")

    def test_commands_are_rejected_while_a_task_is_running(self) -> None:
        window = self._window()
        release = threading.Event()
        window._executor.submit("Holding", release.wait, lambda _v: None, lambda _e: None)
        try:
            self.assertFalse(window._dispatch_application_action("section.compute"))
            self.assertIn("Busy", window.statusBar().currentMessage())
            self.assertFalse(window._dispatch_framework_action("file.new_project"))
            result = window._command_result("section.add_plane", {"axis": "Z", "offset": 0.0})
            self.assertFalse(result.success)
            window.set_project_dirty(False)
            event = QCloseEvent()
            window.closeEvent(event)
            self.assertFalse(event.isAccepted(), "closing must be refused while a task runs")
        finally:
            release.set()
            self.assertTrue(pump(lambda: not window._executor.busy))

    def test_section_compute_runs_in_the_background_and_adds_curves(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            self._open(window, directory)
        state = window.composition.state
        self.assertTrue(window._dispatch_application_action("section.add_plane", {"axis": "Z", "offset": 1.0}))

        threads: list[threading.Thread] = []
        original = window.composition.workflow.section.compute_section

        def spy(*args, **kwargs):
            threads.append(threading.current_thread())
            return original(*args, **kwargs)

        window.composition.workflow.section.compute_section = spy  # type: ignore[method-assign]
        self.assertTrue(window._dispatch_application_action("section.compute"))
        self.assertTrue(pump(lambda: bool(state.curve_collection.curves)))
        self.assertIsNot(threads[0], threading.main_thread())
        self.assertEqual(len(state.curve_collection.curves), 1)
        self.assertTrue(state.curve_collection.curves[0].is_closed)
        self.assertEqual(self.errors, [])


if __name__ == "__main__":
    unittest.main()
