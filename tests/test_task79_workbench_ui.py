from __future__ import annotations

import ast
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "packages" / "workbench_ui"
sys.path.insert(0, str(PACKAGE_ROOT))

from PySide6.QtWidgets import QApplication  # noqa: E402

from workbench_ui import (  # noqa: E402
    ActionDefinition,
    ActionRegistry,
    CommandPalette,
    FieldDefinition,
    FrameworkSettings,
    PropertyInspectorModel,
    SceneNode,
    SceneTreeModel,
    ToolModeManager,
    ThemeManager,
)


class Task79ContractTests(unittest.TestCase):
    def test_actions_propagate_state_and_palette_search(self) -> None:
        registry = ActionRegistry([ActionDefinition("view.frame_all", "Frame All", category="View")])
        palette = CommandPalette(registry)
        self.assertEqual([item.id for item in palette.search("frame")], ["view.frame_all"])
        registry.update("view.frame_all", enabled=False)
        self.assertEqual(palette.search("frame"), ())

    def test_shortcut_conflicts_are_reported_case_insensitively(self) -> None:
        registry = ActionRegistry(
            [
                ActionDefinition("edit.first", "First", shortcut="Ctrl+K"),
                ActionDefinition("edit.second", "Second", shortcut="ctrl+k"),
            ]
        )

        self.assertEqual(
            registry.shortcut_conflicts(),
            {"ctrl+k": ("edit.first", "edit.second")},
        )

    def test_tree_selection_visibility_and_rename(self) -> None:
        model = SceneTreeModel([SceneNode("root", "Root", renameable=False), SceneNode("child", "Child", parent_id="root")])
        selection = model.select(["child"])
        self.assertEqual(selection.primary_id, "child")
        model.set_visible("child", False)
        self.assertFalse(model.nodes["child"].visible)
        model.rename("child", "Renamed")
        self.assertEqual(model.nodes["child"].label, "Renamed")
        with self.assertRaises(ValueError):
            model.rename("root", "No")

    def test_tree_removal_cascades_and_reorder_stays_within_parent(self) -> None:
        model = SceneTreeModel(
            [
                SceneNode("root", "Root", renameable=False),
                SceneNode("a", "A", parent_id="root", reorderable=True),
                SceneNode("a-child", "A child", parent_id="a"),
                SceneNode("b", "B", parent_id="root", reorderable=True),
            ]
        )
        model.reorder("b", "a")
        self.assertEqual([item.id for item in model.children("root")], ["b", "a"])
        removed = set(model.remove(("a",)))
        self.assertEqual(removed, {"a", "a-child"})

    def test_property_inspector_supports_validation_and_apply_cancel_modes(self) -> None:
        model = PropertyInspectorModel(
            [
                FieldDefinition(
                    "quality",
                    "Quality",
                    "Medium",
                    "combo",
                    options=("Low", "Medium", "High"),
                ),
                FieldDefinition(
                    "opacity",
                    "Opacity",
                    0.5,
                    "slider",
                    validator=lambda value: None if 0 <= float(value) <= 1 else "Out of range",
                ),
                FieldDefinition("count", "Count", 5, "readonly", read_only=True),
            ],
            mode="apply",
        )
        model.set_value("quality", "High")
        self.assertEqual(model.value("quality"), "High")
        self.assertEqual(model.fields[0].value, "Medium")
        self.assertEqual(model.apply(), {"quality": "High"})
        with self.assertRaisesRegex(ValueError, "Out of range"):
            model.set_value("opacity", 2.0)
        with self.assertRaisesRegex(ValueError, "Read-only"):
            model.set_value("count", 6)
        model.set_value("quality", "Low")
        model.cancel()
        self.assertEqual(model.value("quality"), "High")

    def test_tool_lifecycle_and_settings_round_trip(self) -> None:
        manager = ToolModeManager()
        manager.enter("manual", "Place points")
        manager.apply()
        self.assertEqual(manager.state.phase, "applied")
        settings = FrameworkSettings(layout_state=b"layout")
        restored = FrameworkSettings.from_json(settings.to_json())
        self.assertEqual(restored.layout_state, b"layout")
        with self.assertRaisesRegex(ValueError, "corrupt"):
            FrameworkSettings.from_json('{"layout_state":"not-hex"}')

    def test_built_in_themes_have_complete_shell_styles(self) -> None:
        manager = ThemeManager(ThemeManager.built_in("light"))
        stylesheet = manager.stylesheet()
        self.assertIn("QMainWindow", stylesheet)
        self.assertIn("#ffffff", stylesheet)
        with self.assertRaises(ValueError):
            ThemeManager.built_in("unknown")

    def test_qt_offscreen_shell_and_vtk_host_are_constructible(self) -> None:
        app = QApplication.instance() or QApplication([])
        from workbench_ui import ApplicationShell, VTKViewportWidget

        shell = ApplicationShell(action_registry=ActionRegistry([ActionDefinition("demo.action", "Action")]))
        viewport = VTKViewportWidget(shell)
        shell.set_workspace(viewport)
        self.assertIs(shell.centralWidget(), viewport)
        self.assertIsNotNone(app)
        shell.deleteLater()

    def test_framework_python_files_do_not_import_host_application(self) -> None:
        for path in PACKAGE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                else:
                    continue
                self.assertFalse(any(name.startswith("app") or name.startswith("application") for name in names), path)


if __name__ == "__main__":
    unittest.main()
