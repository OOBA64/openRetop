"""Surface Sketch: clicking a fresh curve's first point closes it (found driving the window
as a user: the hint promised it, but only curves started on an existing point could close)."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from test_section_sketch import _composition_with


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class CloseByClickTests(unittest.TestCase):
    def test_click_on_the_first_point_closes_the_curve(self) -> None:
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        QApplication.instance() or QApplication([])
        composition = _composition_with("housing")
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        modeling = composition.modeling_controller
        self.assertTrue(window._dispatch_application_action("model.sketch"))
        for point in ((-25.0, -15.0, 12.5), (25.0, -15.0, 12.5), (25.0, 15.0, 12.5), (-25.0, 15.0, 12.5)):
            self.assertTrue(modeling.sketch_click(point).success)
        first = modeling.session.sketch_points[0][1]

        def project(points: object) -> np.ndarray:
            # the first point is where the click lands (200, 150); anything else far away
            values = np.asarray(points, dtype=float).reshape(-1, 3)
            return np.array([[203.0, 148.0] if np.allclose(value, first) else [900.0, 900.0] for value in values])

        window.viewport._last_pointer_release_was_click = True
        with patch.object(window.viewport, "project_points", side_effect=project):
            window._on_viewport_pointer("left_release", 200, 150, None)
        (curve,) = composition.state.model.sketch.curves
        self.assertTrue(curve.closed)
        self.assertEqual(len(curve.nodes), 4)


if __name__ == "__main__":
    unittest.main()
