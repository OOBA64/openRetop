from __future__ import annotations

from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]


class Task81SupportedEntryPointTests(unittest.TestCase):
    def test_supported_entry_point_is_v3_only(self) -> None:
        source = (ROOT / "src" / "main.py").read_text(encoding="utf-8")
        self.assertIn("presentation.qt.main_window", source)
        self.assertNotIn("app.main_window", source)
        self.assertNotIn("tkinter", source)

    def test_v3_presentation_does_not_import_tk(self) -> None:
        for path in (ROOT / "src").rglob("*.py"):
            source = path.read_text(encoding="utf-8")
            self.assertNotIn("tkinter", source, path)

    def test_legacy_shell_viewport_and_compatibility_package_are_physically_absent(self) -> None:
        self.assertFalse((ROOT / "src" / "app" / "main_window.py").exists())
        self.assertFalse((ROOT / "src" / "app" / "scene_browser.py").exists())
        self.assertFalse((ROOT / "src" / "app" / "menus.py").exists())
        self.assertFalse((ROOT / "src" / "app" / "preferences_dialog.py").exists())
        self.assertFalse((ROOT / "src" / "viewer" / "embedded_viewport.py").exists())

    def test_production_has_no_legacy_app_imports(self) -> None:
        violations: list[tuple[Path, int, str]] = []
        for path in (ROOT / "src").rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    modules = [node.module or ""]
                else:
                    continue
                violations.extend(
                    (path, node.lineno, module)
                    for module in modules
                    if module == "app" or module.startswith("app.")
                )
        self.assertEqual(violations, [])

    def test_v3_viewport_uses_shared_snapshot_synchronizer(self) -> None:
        source = (ROOT / "src" / "presentation" / "qt" / "viewport.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SceneSynchronizer", source)
        self.assertIn("VTKActorAdapter", source)
        self.assertIn("SceneSnapshot", source)


if __name__ == "__main__":
    unittest.main()
