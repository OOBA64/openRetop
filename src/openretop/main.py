"""Desktop entry point for openRetop."""

from __future__ import annotations


def main() -> int:
    from openretop.presentation.qt.main_window import run_v3_app

    return run_v3_app()


run_app = main


if __name__ == "__main__":
    raise SystemExit(main())
