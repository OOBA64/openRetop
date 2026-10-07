"""UX-06: every action has a tooltip, and disabled actions say what they need."""

from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path

import trimesh
from PySide6.QtWidgets import QApplication

from openretop.application.actions import CONDITION_REQUIREMENTS, CORE_ACTIONS, ActionCondition, ActionContext
from openretop.bootstrap import create_application
from openretop.infrastructure.settings_repository import InMemorySettingsRepository
from openretop.presentation.qt.background import ThreadedExecutor
from openretop.presentation.qt.main_window import OpenRetopV3Window


class ConditionReasonTests(unittest.TestCase):
    def test_every_condition_has_a_plain_language_requirement(self) -> None:
        missing = [c for c in ActionCondition if c is not ActionCondition.ALWAYS and c not in CONDITION_REQUIREMENTS]
        self.assertEqual(missing, [])

    def test_unmet_requirements_name_exactly_what_is_missing(self) -> None:
        compute = next(item for item in CORE_ACTIONS if item.id == "section.compute")
        reasons = compute.unmet_requirements(ActionContext())
        self.assertTrue(any("loaded scan" in reason for reason in reasons), reasons)
        self.assertEqual(compute.unmet_requirements(ActionContext(mesh_loaded=True, has_section_plane=True)), ())


class ActionTooltipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def _window(self, **kwargs) -> OpenRetopV3Window:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()), **kwargs)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        return window

    def test_every_action_has_a_description_and_tooltip(self) -> None:
        window = self._window()
        for definition in window._framework_actions.definitions:
            if definition.id.startswith("file.recent."):
                continue
            self.assertTrue(definition.description.strip(), f"{definition.id} has no description")
            self.assertIn(definition.label, window._qt_actions[definition.id].toolTip())

    def test_disabled_compute_section_explains_it_needs_a_scan(self) -> None:
        window = self._window()
        action = window._qt_actions["section.compute"]
        self.assertFalse(action.isEnabled())
        self.assertIn("loaded scan", action.toolTip())
        self.assertIn("Unavailable", action.toolTip())

    def test_tooltip_loses_the_reason_once_the_action_is_available(self) -> None:
        window = self._window()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ball.stl"
            trimesh.creation.icosphere(subdivisions=2, radius=10).export(path)
            window.open_model_path(path, units="mm")
        window._sync_action_state()
        action = window._qt_actions["section.compute"]
        self.assertTrue(action.isEnabled())
        self.assertNotIn("Unavailable", action.toolTip())

    def test_shortcut_is_shown_in_the_tooltip(self) -> None:
        window = self._window()
        self.assertIn("Ctrl+O", window._qt_actions["file.open_model"].toolTip())

    def test_menu_entries_show_tooltips(self) -> None:
        window = self._window()
        self.assertTrue(all(action.menu().toolTipsVisible() for action in window.menuBar().actions()))

    def test_actions_are_disabled_while_a_background_task_runs(self) -> None:
        window = self._window(executor=ThreadedExecutor())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ball.stl"
            trimesh.creation.icosphere(subdivisions=2, radius=10).export(path)
            window.open_model_path(path, units="mm")
            import time

            deadline = time.monotonic() + 20
            while window.composition.state.mesh_object is None and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.005)
        window._sync_action_state()
        release = threading.Event()
        window._executor.submit("Holding", release.wait, lambda _v: None, lambda _e: None)
        QApplication.processEvents()
        try:
            action = window._qt_actions["section.compute"]
            self.assertFalse(action.isEnabled())
            self.assertIn("current task", action.toolTip())
        finally:
            release.set()
            deadline = time.monotonic() + 10
            while window._executor.busy and time.monotonic() < deadline:
                QApplication.processEvents()
                time.sleep(0.005)
        QApplication.processEvents()
        self.assertTrue(window._qt_actions["section.compute"].isEnabled())


if __name__ == "__main__":
    unittest.main()


class ActionCatalogueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_help_text_and_view_shortcuts_refer_to_real_actions(self) -> None:
        from openretop.application import actions

        ids = {item.id for item in CORE_ACTIONS}
        self.assertEqual(set(actions._DESCRIPTIONS) - ids, set())
        self.assertEqual(set(actions._VIEW_SHORTCUTS) - ids, set())

    def test_primary_commands_have_specific_descriptions(self) -> None:
        generic = [
            item.id
            for item in CORE_ACTIONS
            if item.id in {"section.compute", "section.add_plane", "region.start", "manual_curve.create", "surface.editable_brep_loft"}
            and item.description.endswith("in the current workflow.")
        ]
        self.assertEqual(generic, [])

    def test_no_shortcut_is_bound_to_two_actions(self) -> None:
        window = OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))
        self.addCleanup(window.close)
        self.assertEqual(window._framework_actions.shortcut_conflicts(), {})
        self.assertEqual(window._framework_actions.require("view.frame_all").shortcut, "Home")
        self.assertEqual(window._framework_actions.require("view.named.top").shortcut, "Ctrl+5")
