"""Desktop entry point for openRetop."""

from __future__ import annotations

from pathlib import Path
import sys


def _ensure_workbench_ui_path() -> None:
    framework_path = Path(__file__).resolve().parents[1] / "packages" / "workbench_ui"
    if framework_path.exists() and str(framework_path) not in sys.path:
        sys.path.insert(0, str(framework_path))


_ensure_workbench_ui_path()

from presentation.qt.main_window import run_v3_app

run_app = run_v3_app


def main() -> int:
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
