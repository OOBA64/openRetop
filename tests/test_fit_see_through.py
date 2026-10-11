"""H-03: while Fit Surface is open, the surfaces already made are see-through, so the scan
behind them - the next area to pick - shows. Bodies and other tools stay opaque."""

from __future__ import annotations

import unittest

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from test_section_sketch import _composition_with


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class SeeThroughWhileFittingTests(unittest.TestCase):
    def test_surfaces_are_see_through_only_while_fitting(self) -> None:
        from PySide6.QtWidgets import QApplication

        from openretop.cad_kernel import jobs
        from openretop.cad_kernel.surfacing import plane_patch
        from openretop.modeling.document import entity_from_result
        from openretop.presentation.qt.main_window import OpenRetopV3Window
        from openretop.presentation.qt.surfacing_workbench import FITTING_SURFACE_OPACITY
        from openretop.viewer.modeling_scene import modeling_items

        QApplication.instance() or QApplication([])
        composition = _composition_with("housing")
        model = composition.state.model
        face = plane_patch((0.0, 0.0, 1.0), (0.0, 0.0, 12.5), [(-20, -10, 12.5), (20, 10, 12.5), (20, -10, 12.5)])
        plane = model.add(entity_from_result(model, jobs.surface_result(face, kind="plane", rms=0.01, max_error=0.02), tool="fit_surface"))
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))

        def opacity() -> float:
            faces, _edges, _overlays = modeling_items(window._modeling_scene_input(), composition.state.mesh_object)
            return next(item.style.opacity for item in faces if item.id == f"model-face:{plane.id}")

        self.assertEqual(opacity(), 1.0)
        self.assertTrue(window._dispatch_application_action("model.fit_surface"))
        self.assertLess(FITTING_SURFACE_OPACITY, 1.0)
        self.assertEqual(opacity(), FITTING_SURFACE_OPACITY)
        composition.modeling_controller.finish()
        self.assertEqual(opacity(), 1.0)


if __name__ == "__main__":
    unittest.main()
