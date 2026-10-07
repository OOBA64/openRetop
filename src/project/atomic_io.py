"""Crash-safe file writing."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def write_text_atomic(path: str | Path, text: str, *, encoding: str = "utf-8") -> None:
    """Write ``text`` to ``path`` so a failure never leaves a truncated file.

    The data goes to a temporary file in the same directory (so the final
    rename stays on one filesystem), is flushed to disk, and then replaces the
    target with ``os.replace``. The previous file survives any earlier failure.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        dir=target.parent, prefix=f".{target.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding=encoding, newline="\n") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, target)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
