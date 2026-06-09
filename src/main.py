"""Desktop entry point for openRetop."""

from __future__ import annotations

from app.main_window import run_app


def main() -> int:
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
