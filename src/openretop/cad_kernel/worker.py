"""Run CAD kernel operations in a separate process (S-03).

OpenCASCADE can crash the interpreter (an access violation on a near-tangent intersection) or
hang (the mesher on a pathological surface). Neither may take the application down, so
modelling operations run in a long-lived worker process:

- a call is a job name from ``cad_kernel.jobs`` plus picklable arguments (NumPy arrays, BREP
  bytes, numbers, dicts)
- a reply that does not arrive within the timeout kills the worker; a worker that dies
  mid-job is noticed by the broken pipe. Either way the caller gets a failed ``KernelReply``
  with a plain reason, and the next call starts a fresh worker.

``inline=True`` runs jobs in the calling process (tests, and environments without process
support); it gives the same replies but no isolation.
"""

from __future__ import annotations

import multiprocessing
import threading
import time
import traceback
from dataclasses import dataclass
from typing import Any

DEFAULT_TIMEOUT = 120.0


@dataclass
class KernelReply:
    ok: bool
    value: Any = None
    error: str = ""
    crashed: bool = False
    timed_out: bool = False
    seconds: float = 0.0


def _run_job(name: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
    from openretop.cad_kernel import jobs

    job = getattr(jobs, name, None)
    if job is None or name.startswith("_") or name not in jobs.JOBS:
        raise ValueError(f"unknown kernel job: {name}")
    return job(*args, **kwargs)


def _serve(connection: Any) -> None:  # pragma: no cover - runs in the child process
    while True:
        try:
            message = connection.recv()
        except (EOFError, OSError):
            return
        if message is None:
            return
        name, args, kwargs = message
        try:
            connection.send(("ok", _run_job(name, args, kwargs)))
        except Exception as exc:  # report every job failure to the parent as data
            connection.send(("error", f"{exc}", traceback.format_exc()))


class KernelWorker:
    def __init__(self, *, inline: bool = False, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.inline = inline
        self.timeout = timeout
        self._process: Any = None
        self._connection: Any = None
        self._lock = threading.Lock()  # one job at a time (UI thread and a background thread)
        self.restarts = 0

    # -- public ------------------------------------------------------------------------------

    def call(self, name: str, *args: Any, timeout: float | None = None, **kwargs: Any) -> KernelReply:
        started = time.perf_counter()
        if self.inline:
            try:
                value = _run_job(name, args, kwargs)
            except Exception as exc:
                return KernelReply(False, error=str(exc) or type(exc).__name__, seconds=time.perf_counter() - started)
            return KernelReply(True, value, seconds=time.perf_counter() - started)
        with self._lock:
            return self._call_process(name, args, kwargs, timeout or self.timeout, started)

    def shutdown(self) -> None:
        with self._lock:
            self._stop()

    @property
    def alive(self) -> bool:
        return self._process is not None and self._process.is_alive()

    # -- internals ---------------------------------------------------------------------------

    def _call_process(self, name: str, args: tuple[Any, ...], kwargs: dict[str, Any], timeout: float, started: float) -> KernelReply:
        try:
            self._ensure_started()
            self._connection.send((name, args, kwargs))
            if not self._connection.poll(timeout):
                self._stop()
                return KernelReply(
                    False,
                    error=f"the CAD kernel did not finish within {timeout:.0f} s and was stopped; try simpler input",
                    timed_out=True,
                    seconds=time.perf_counter() - started,
                )
            reply = self._connection.recv()
        except (EOFError, OSError, BrokenPipeError):
            self._stop()
            return KernelReply(
                False,
                error="the CAD kernel crashed on this input (the application is unaffected); try other settings",
                crashed=True,
                seconds=time.perf_counter() - started,
            )
        seconds = time.perf_counter() - started
        if reply[0] == "ok":
            return KernelReply(True, reply[1], seconds=seconds)
        return KernelReply(False, error=reply[1] or "the CAD kernel reported an error", seconds=seconds)

    def _ensure_started(self) -> None:
        if self._process is not None and self._process.is_alive():
            return
        self._stop()
        context = multiprocessing.get_context("spawn")
        parent, child = context.Pipe()
        process = context.Process(target=_serve, args=(child,), name="openretop-kernel", daemon=True)
        process.start()
        child.close()
        self._process, self._connection = process, parent
        self.restarts += 1

    def _stop(self) -> None:
        process, connection = self._process, self._connection
        self._process = self._connection = None
        if connection is not None:
            try:
                connection.close()
            except OSError:
                pass
        if process is not None:
            if process.is_alive():
                process.kill()
            process.join(timeout=5)


__all__ = ("DEFAULT_TIMEOUT", "KernelReply", "KernelWorker")
