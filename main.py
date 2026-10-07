"""Convenience launcher: ``python main.py`` runs openRetop from a source checkout.

The installed equivalents are ``openretop`` and ``python -m openretop``.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for _path in (ROOT / "src", ROOT / "packages" / "workbench_ui"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from openretop.main import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
