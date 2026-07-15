from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Task81SupportedEntryPointTests(unittest.TestCase):
    def test_supported_entry_point_is_v3_only(self) -> None:
        source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        self.assertIn("presentation.qt.main_window", source)
        self.assertNotIn("app.main_window", source)
        self.assertNotIn("tkinter", source)

    def test_v3_presentation_does_not_import_tk(self) -> None:
        for path in (ROOT / "src" / "presentation").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("tkinter", source, path)

    def test_v3_viewport_uses_shared_snapshot_synchronizer(self) -> None:
        source = (ROOT / "src" / "presentation" / "qt" / "viewport.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SceneSynchronizer", source)
        self.assertIn("VTKActorAdapter", source)
        self.assertIn("SceneSnapshot", source)


if __name__ == "__main__":
    unittest.main()
