from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import trimesh

ROOT = Path(__file__).resolve().parents[1]

from PySide6.QtWidgets import QApplication  # noqa: E402

from openretop.application.state import AppState  # noqa: E402
from openretop.bootstrap import create_application  # noqa: E402
from openretop.cad_kernel.export_step import export_step  # noqa: E402
from openretop.geometry.tolerances import (  # noqa: E402
    curve_fit_tolerance,
    curve_join_tolerance,
    curve_simplify_tolerance,
)
from openretop.infrastructure.settings_repository import InMemorySettingsRepository  # noqa: E402
from openretop.presentation.qt.main_window import OpenRetopV3Window  # noqa: E402
from openretop.project.project_data import default_project_data  # noqa: E402
from openretop.project.project_session import restore_project_state  # noqa: E402
from openretop.project.project_state import project_from_app_state  # noqa: E402
from openretop.settings.settings_data import default_app_settings  # noqa: E402
from openretop.settings.settings_io import settings_from_dict, settings_to_dict  # noqa: E402

try:
    import cadquery as cq

    HAVE_CADQUERY = True
except ImportError:  # pragma: no cover
    HAVE_CADQUERY = False


class ToleranceUnitTests(unittest.TestCase):
    def test_floor_is_the_same_physical_size_in_every_unit(self) -> None:
        mm = curve_fit_tolerance(0.0, "mm")
        self.assertAlmostEqual(curve_fit_tolerance(0.0, "in") * 25.4, mm)
        self.assertAlmostEqual(curve_fit_tolerance(0.0, "m") * 1000.0, mm)

    def test_relative_part_dominates_for_large_models(self) -> None:
        self.assertAlmostEqual(curve_fit_tolerance(2000.0, "mm"), 1.0)

    def test_repair_and_simplify_defaults_scale_with_units(self) -> None:
        self.assertAlmostEqual(curve_join_tolerance("mm"), 0.01)
        self.assertAlmostEqual(curve_join_tolerance("in") * 25.4, 0.01)
        self.assertAlmostEqual(curve_simplify_tolerance("m") * 1000.0, 0.001)


class SettingsAndProjectUnitTests(unittest.TestCase):
    def test_default_units_round_trip_and_reject_unknown(self) -> None:
        data = settings_to_dict(default_app_settings())
        self.assertEqual(data["import"]["default_units"], "mm")
        data["import"]["default_units"] = "in"
        self.assertEqual(settings_from_dict(data).import_settings.default_units, "in")
        data["import"]["default_units"] = "cubit"
        with self.assertRaises(ValueError):
            settings_from_dict(data)

    def test_units_survive_project_state_round_trip(self) -> None:
        state = AppState()
        project = project_from_app_state(
            mesh_object=None,
            proxy_quality="Medium",
            show_grid=True,
            show_axes=True,
            show_normals=False,
            section_axis="Z",
            section_offset=0.0,
            show_section_plane=False,
            units="in",
        )
        self.assertEqual(project.units, "in")
        restore_project_state(state, project)
        self.assertEqual(state.units, "in")
        self.assertFalse(state.units_assumed)

    def test_migrated_project_marks_units_as_assumed(self) -> None:
        project = default_project_data()
        project.units_assumed = True
        state = AppState()
        restore_project_state(state, project)
        self.assertTrue(state.units_assumed)


@unittest.skipUnless(HAVE_CADQUERY, "cadquery not installed")
class StepUnitTests(unittest.TestCase):
    def _export(self, units: str) -> str:
        box = cq.Workplane().box(25.4, 25.4, 25.4).val()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "part.step"
            result = export_step(box, path, units)
            self.assertTrue(result.success, result.reason)
            return path.read_text(encoding="utf-8", errors="replace")

    def test_step_file_declares_the_project_unit(self) -> None:
        self.assertIn("SI_UNIT(.MILLI.,.METRE.)", self._export("mm"))
        self.assertIn("CONVERSION_BASED_UNIT('INCH'", self._export("in"))
        metres = self._export("m")
        self.assertIn("SI_UNIT($,.METRE.)", metres)
        self.assertNotIn("MILLI", metres.split("CARTESIAN_POINT")[0].split("LENGTH_UNIT")[0][-200:])

    def test_numbers_are_not_rescaled_only_labelled(self) -> None:
        text = self._export("in")
        points = re.findall(r"CARTESIAN_POINT\('',\(([^)]*)\)", text)
        self.assertTrue(any("12.7" in point for point in points))

    def test_exporter_restores_default_unit_afterwards(self) -> None:
        self._export("in")
        self.assertIn("SI_UNIT(.MILLI.,.METRE.)", self._export("mm"))

    def test_unknown_unit_is_a_failed_result_not_an_exception(self) -> None:
        box = cq.Workplane().box(1, 1, 1).val()
        with tempfile.TemporaryDirectory() as directory:
            result = export_step(box, Path(directory) / "x.step", "furlong")
        self.assertFalse(result.success)


class WindowUnitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    @staticmethod
    def _window() -> OpenRetopV3Window:
        return OpenRetopV3Window(create_application(settings_repository=InMemorySettingsRepository()))

    def test_import_units_are_stored_saved_and_restored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mesh_path = Path(directory) / "part.stl"
            trimesh.creation.box(extents=(1.0, 2.0, 3.0)).export(mesh_path)
            project_path = Path(directory) / "job.openretop"

            window = self._window()
            try:
                self.assertTrue(window.open_model_path(mesh_path, units="in"))
                self.assertEqual(window.composition.state.units, "in")
                self.assertEqual(len(window.composition.state.mesh_object.source_mesh.vertices), 8)
                with patch(
                    "openretop.presentation.qt.main_window.QFileDialog.getSaveFileName",
                    return_value=(str(project_path), ""),
                ):
                    self.assertTrue(window.save_project(as_dialog=True))
            finally:
                window.close()

            reopened = self._window()
            try:
                self.assertTrue(reopened.open_project_path(project_path))
                self.assertEqual(reopened.composition.state.units, "in")
                self.assertFalse(reopened.composition.state.units_assumed)
            finally:
                reopened.close()

    def test_cancelling_the_unit_prompt_aborts_the_import(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            mesh_path = Path(directory) / "part.stl"
            trimesh.creation.box().export(mesh_path)
            window = self._window()
            try:
                window._ask_units = lambda *args, **kwargs: None  # type: ignore[method-assign]
                self.assertFalse(window.open_model_path(mesh_path))
                self.assertIsNone(window.composition.state.mesh_object)
            finally:
                window.close()

    def test_set_model_units_relabels_and_dirties_the_project(self) -> None:
        window = self._window()
        try:
            window._ask_units = lambda *args, **kwargs: "m"  # type: ignore[method-assign]
            window.composition.state.units_assumed = True
            self.assertTrue(window.set_model_units())
            self.assertEqual(window.composition.state.units, "m")
            self.assertFalse(window.composition.state.units_assumed)
            self.assertTrue(window.project_dirty)
        finally:
            window.set_project_dirty(False)  # closing a dirty window would prompt
            window.close()


if __name__ == "__main__":
    unittest.main()
