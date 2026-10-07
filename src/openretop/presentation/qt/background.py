"""Run slow work off the UI thread and deliver the outcome back on it.

Two interchangeable executors share one interface:

* ``ThreadedExecutor`` runs ``work`` on a worker thread and calls the callbacks
  on the UI thread (through a queued Qt signal), so the window keeps painting.
* ``InlineExecutor`` runs everything immediately on the calling thread. It is
  the default so scripts and tests stay synchronous and deterministic.

Only one task runs at a time. ``work`` must not touch widgets; while a task is
running the window rejects commands that would mutate application state.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

LOGGER = logging.getLogger(__name__)

Work = Callable[[], object]
DoneCallback = Callable[[object], None]
ErrorCallback = Callable[[BaseException], None]


class TaskExecutor(Protocol):
    @property
    def busy(self) -> bool: ...

    @property
    def asynchronous(self) -> bool: ...

    @property
    def label(self) -> str: ...

    def submit(
        self,
        label: str,
        work: Work,
        on_done: DoneCallback,
        on_error: ErrorCallback,
    ) -> bool:
        """Start ``work``; return False (and do nothing) if a task is running."""


class InlineExecutor:
    """Synchronous executor: ``work`` and the callback run before ``submit`` returns."""

    asynchronous = False

    def __init__(self) -> None:
        self._label = ""

    @property
    def busy(self) -> bool:
        return False

    @property
    def label(self) -> str:
        return self._label

    def submit(self, label: str, work: Work, on_done: DoneCallback, on_error: ErrorCallback) -> bool:
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001 - reported through the callback
            on_error(exc)
        else:
            on_done(result)
        return True


@dataclass(frozen=True)
class _Outcome:
    result: object = None
    error: BaseException | None = None


class _Runnable(QRunnable):
    def __init__(self, work: Work, deliver: Callable[[_Outcome], None]) -> None:
        super().__init__()
        self._work = work
        self._deliver = deliver
        self.setAutoDelete(True)

    def run(self) -> None:  # runs on a pool thread
        try:
            outcome = _Outcome(result=self._work())
        except BaseException as exc:  # noqa: BLE001 - must cross the thread boundary
            LOGGER.debug("Background task failed", exc_info=True)
            outcome = _Outcome(error=exc)
        self._deliver(outcome)


class ThreadedExecutor(QObject):
    """Worker-thread executor; callbacks are invoked on this object's (UI) thread."""

    asynchronous = True
    _delivered = Signal(object)
    busy_changed = Signal(bool)

    def __init__(self, parent: QObject | None = None, pool: QThreadPool | None = None) -> None:
        super().__init__(parent)
        self._pool = pool or QThreadPool.globalInstance()
        self._busy = False
        self._label = ""
        self._on_done: DoneCallback | None = None
        self._on_error: ErrorCallback | None = None
        self._delivered.connect(self._finish)

    @property
    def busy(self) -> bool:
        return self._busy

    @property
    def label(self) -> str:
        return self._label

    def submit(self, label: str, work: Work, on_done: DoneCallback, on_error: ErrorCallback) -> bool:
        if self._busy:
            return False
        self._busy = True
        self._label = label
        self._on_done, self._on_error = on_done, on_error
        self.busy_changed.emit(True)
        self._pool.start(_Runnable(work, self._delivered.emit))
        return True

    def wait_idle(self, timeout_ms: int = 30_000) -> bool:
        """Block until the pool is idle (used when closing the window)."""

        return bool(self._pool.waitForDone(timeout_ms))

    def _finish(self, outcome: _Outcome) -> None:
        on_done, on_error = self._on_done, self._on_error
        self._busy = False
        self._label = ""
        self._on_done = self._on_error = None
        self.busy_changed.emit(False)
        try:
            if outcome.error is not None:
                if on_error is not None:
                    on_error(outcome.error)
            elif on_done is not None:
                on_done(outcome.result)
        except Exception:  # noqa: BLE001 - never let a callback kill the event loop
            LOGGER.exception("Background task callback failed")
