"""H-01 Align to World in the application: a tilted bracket scan squared to the world in
two clicks plus Apply, everything built on it moving along, one undo step."""

from __future__ import annotations

import unittest

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from openretop.application.transform_math import rotation_matrix
from openretop.modeling.alignment import apply_points
from test_surfacing_workflow import _composition, _install

TILT_ANGLES = np.array([17.0, -23.0, 31.0])
TILT_SHIFT = np.array([12.0, -40.0, 7.5])


def _tilt() -> np.ndarray:
    matrix = np.identity(4)
    matrix[:3, :3] = rotation_matrix(TILT_ANGLES)
    matrix[:3, 3] = TILT_SHIFT
    return matrix


def _bracket():
    from openretop.benchmarks import make_part, scan_from_part

    part = make_part("bracket")
    return part, scan_from_part(part, noise_sigma=0.02, seed=1, edge_length=1.0)


def _seed(scan, face: int) -> int:
    """The triangle of a face farthest from its edges (where a user clicks)."""

    from scipy.spatial import cKDTree

    vertices, triangles = np.asarray(scan.vertices), np.asarray(scan.triangles)
    centers = vertices[triangles].mean(axis=1)
    inside = scan.face_labels == face
    distance, _ = cKDTree(centers[~inside]).query(centers[inside])
    return int(np.flatnonzero(inside)[int(np.argmax(distance))])


def _angle_to_axis(direction: np.ndarray) -> float:
    direction = direction / np.linalg.norm(direction)
    return float(np.degrees(np.arccos(np.clip(np.max(np.abs(direction)), -1.0, 1.0))))


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class AlignBracketTests(unittest.TestCase):
    TOP, SIDE, HOLE = 1, 5, 12  # top (z = 5), front side (y = -25), the boss hole (axis (20, 0))

    def _align(self, *, baked: bool):
        part, scan = _bracket()
        composition = _composition()
        vertices = np.asarray(scan.vertices, dtype=float)
        if baked:  # tilted in the file
            _install(composition, apply_points(_tilt(), vertices), scan.triangles)
        else:  # tilted by the scan's pose (Move / Rotate)
            _install(composition, vertices, scan.triangles)
            mesh = composition.state.mesh_object
            mesh.rotation, mesh.location = TILT_ANGLES.copy(), TILT_SHIFT.copy()
            composition.transform_controller._apply_object_transform()
        modeling = composition.modeling_controller
        self.assertTrue(composition.workflow.dispatch("model.align", {}).success)
        for face in (self.TOP, self.SIDE, self.HOLE):
            result = modeling.align_pick(_seed(scan, face))
            self.assertTrue(result.success, result.errors)
        session = modeling.session
        self.assertEqual([feature.kind for feature in session.align_features], ["plane", "plane", "axis"])
        applied = composition.workflow.dispatch("model.align_apply", {})
        self.assertTrue(applied.success, applied.errors)
        self.assertTrue(applied.status.startswith("Aligned:"), applied.status)
        self.assertIsNone(modeling.session)
        return part, scan, composition

    def test_two_faces_and_a_hole_square_a_tilted_scan_baked_in_the_file(self) -> None:
        _part, scan, composition = self._align(baked=True)
        net = composition.transform_controller.current_object_matrix() @ _tilt()  # part frame -> aligned world
        top = net[:3, :3] @ np.array([0.0, 0.0, 1.0])
        side = net[:3, :3] @ np.array([0.0, -1.0, 0.0])
        self.assertLess(_angle_to_axis(top), 0.05)
        self.assertLess(_angle_to_axis(side), 0.05)
        np.testing.assert_allclose(top, (0.0, 0.0, 1.0), atol=1e-3)  # the clicked face is the top
        # the origin: on the hole's axis (X, Y) and on the top face (Z)
        np.testing.assert_allclose(apply_points(net, (20.0, 0.0, 5.0)), 0.0, atol=0.05)

    def test_the_same_through_the_scans_pose_and_undo_puts_it_back(self) -> None:
        _part, _scan, composition = self._align(baked=False)
        mesh = composition.state.mesh_object
        net = composition.transform_controller.current_object_matrix()
        self.assertLess(_angle_to_axis(net[:3, :3] @ np.array([0.0, 0.0, 1.0])), 0.05)
        composition.workflow.dispatch("edit.undo", {})
        np.testing.assert_allclose(mesh.rotation, TILT_ANGLES, atol=1e-9)
        np.testing.assert_allclose(mesh.location, TILT_SHIFT, atol=1e-9)
        composition.workflow.dispatch("edit.redo", {})
        np.testing.assert_allclose(composition.transform_controller.current_object_matrix(), net, atol=1e-9)


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class EverythingMovesTests(unittest.TestCase):
    def test_surfaces_curves_sections_and_measurements_move_with_the_scan(self) -> None:
        from openretop.application.state import Measurement
        from openretop.cad_kernel import jobs

        _part, scan = _bracket()
        composition = _composition()
        _install(composition, apply_points(_tilt(), np.asarray(scan.vertices, dtype=float)), scan.triangles)
        modeling = composition.modeling_controller
        state = composition.state
        # a fitted plane on the top, a Surface Sketch curve, a section cut, a measurement
        self.assertTrue(composition.workflow.dispatch("model.fit_surface", {}).success)
        modeling.select_at(_seed(scan, 1))
        self.assertTrue(composition.workflow.dispatch("model.fit_create", {}).success)
        modeling.finish()
        (plane,) = state.model.entities
        curve = state.model.sketch.add_polyline_curve(np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 0.0], [10.0, 10.0, 0.0]]))
        self.assertTrue(composition.workflow.dispatch("section.add_plane", {}).success)
        self.assertTrue(composition.workflow.dispatch("section.compute", {}).success)
        stored = state.section_collection.results[0]
        cut_before = np.asarray(stored.result.polylines[0].points).copy()
        state.measure.measurements.append(Measurement("m1", (1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
        old_vertices, old_curve = plane.vertices.copy(), curve.polyline.copy()
        # align by any two features
        self.assertTrue(composition.workflow.dispatch("model.align", {}).success)
        modeling.align_pick(_seed(scan, 1))
        modeling.align_pick(_seed(scan, 5))
        matrix = modeling.align_solution().matrix  # type: ignore[union-attr]
        result = composition.workflow.dispatch("model.align_apply", {})
        self.assertTrue(result.success, result.errors)
        curves = len(state.model.sketch.curves)  # ours and the section's
        self.assertIn(f"Moved with it: 1 surface, {curves} curves, 1 section cut and 1 measurement", result.status)
        moved_plane = state.model.get(plane.id)
        np.testing.assert_allclose(moved_plane.vertices, apply_points(matrix, old_vertices), atol=1e-9)  # type: ignore[union-attr]
        shape = jobs.shape(moved_plane.brep)  # the BREP moved too  # type: ignore[union-attr]
        np.testing.assert_allclose(
            np.sort(np.asarray(shape["vertices"]), axis=0)[[0, -1]],
            np.sort(apply_points(matrix, np.asarray(jobs.shape(plane.brep)["vertices"])), axis=0)[[0, -1]],
            atol=1e-6,
        )
        np.testing.assert_allclose(state.model.sketch.curve(curve.id).polyline, apply_points(matrix, old_curve), atol=1e-9)  # type: ignore[union-attr]
        np.testing.assert_allclose(state.section_collection.results[0].result.polylines[0].points, apply_points(matrix, cut_before), atol=1e-9)
        np.testing.assert_allclose(state.measure.measurements[0].start, apply_points(matrix, (1.0, 2.0, 3.0)), atol=1e-9)
        # one undo puts all of it back
        composition.workflow.dispatch("edit.undo", {})
        np.testing.assert_allclose(state.model.get(plane.id).vertices, old_vertices)  # type: ignore[union-attr]
        np.testing.assert_allclose(state.model.sketch.curve(curve.id).polyline, old_curve)  # type: ignore[union-attr]
        np.testing.assert_allclose(state.section_collection.results[0].result.polylines[0].points, cut_before)
        self.assertEqual(state.measure.measurements[0].start, (1.0, 2.0, 3.0))


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class AlignWindowTests(unittest.TestCase):
    def test_the_panel_rows_backspace_and_enter(self) -> None:
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.main_window import OpenRetopV3Window

        QApplication.instance() or QApplication([])
        _part, scan = _bracket()
        composition = _composition()
        _install(composition, apply_points(_tilt(), np.asarray(scan.vertices, dtype=float)), scan.triangles)
        window = OpenRetopV3Window(composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        window._invoke_from_ui("model.align")  # as the toolbar button does
        panel = window.surfacing_panel
        self.assertEqual(panel.title.text(), "Align to World")
        self.assertEqual(window.active_workspace, "scan")
        modeling = composition.modeling_controller
        window._consume_result("model.pointer", modeling.align_pick(_seed(scan, 1)))
        window._consume_result("model.pointer", modeling.align_pick(_seed(scan, 5)))
        self.assertIn("Plane", panel.align_labels[0].text())
        self.assertTrue(panel.align_targets[0].currentText().startswith("Auto (XY)"))
        self.assertTrue(panel.align_apply.isEnabled())
        self.assertEqual(len(window._sketch2d_lines()), 3)  # the X, Y, Z arrows where the axes will go
        self.assertTrue(window._surfacing_key(Qt.Key.Key_Backspace))  # takes back the side face
        self.assertIsNone(modeling.session.align_features[1])
        window._consume_result("model.pointer", modeling.align_pick(_seed(scan, 5)))
        self.assertTrue(window._surfacing_key(Qt.Key.Key_Return))  # applies
        self.assertIsNone(modeling.session)
        self.assertTrue(window.statusBar().currentMessage().startswith("Aligned:"), window.statusBar().currentMessage())


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class MovedSketchTests(unittest.TestCase):
    def test_a_sketch_turned_off_the_world_planes_says_it_cannot_be_edited_yet(self) -> None:
        from openretop.modeling.alignment import moved_frame, world_frame

        _part, scan = _bracket()
        composition = _composition()
        _install(composition, np.asarray(scan.vertices, dtype=float), scan.triangles)
        modeling = composition.modeling_controller
        self.assertTrue(composition.workflow.dispatch("model.section_sketch", {}).success)
        self.assertTrue(composition.workflow.dispatch("model.section_fit", {}).success)
        self.assertTrue(composition.workflow.dispatch("model.section_create", {}).success)
        (profile,) = [entity for entity in composition.state.model.entities if entity.kind == "profile"]
        self.assertTrue(modeling.section_edit_entity(profile.id).success)  # on a world plane: fine
        modeling.finish()
        profile.params["frame"] = moved_frame(world_frame("XY", 0.0), _tilt())
        result = modeling.section_edit_entity(profile.id)
        self.assertFalse(result.success)
        self.assertIn("Align to World", result.errors[0])


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class KernelJobTests(unittest.TestCase):
    def test_transform_shapes_moves_a_box_and_datum_reads_faces(self) -> None:
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder

        from openretop.cad_kernel import jobs
        from openretop.cad_kernel import surfacing as S

        box = S.to_brep(BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape())
        (moved,) = jobs.transform_shapes([box], _tilt().tolist())
        self.assertAlmostEqual(S.shape_volume(S.from_brep(moved)), 6000.0, places=6)
        corner = apply_points(_tilt(), (10.0, 20.0, 30.0))
        vertices = np.asarray(jobs.shape(moved)["vertices"])
        self.assertLess(float(np.min(np.linalg.norm(vertices - corner, axis=1))), 1e-6)
        top = max(S.faces_of(BRepPrimAPI_MakeBox(10.0, 20.0, 30.0).Shape()), key=lambda face: sample_mean_z(face))
        datum = jobs.datum(S.to_brep(top))
        self.assertEqual(datum["kind"], "plane")
        np.testing.assert_allclose(datum["normal"], (0.0, 0.0, 1.0), atol=1e-9)  # out of the box
        side = next(face for face in S.faces_of(BRepPrimAPI_MakeCylinder(4.0, 10.0).Shape()) if S.face_area(face) > 200)
        cylinder = jobs.datum(S.to_brep(side))
        self.assertEqual(cylinder["kind"], "cylinder")
        np.testing.assert_allclose(np.abs(cylinder["axis"]), (0.0, 0.0, 1.0), atol=1e-9)
        with self.assertRaises(ValueError):
            jobs.datum(box)


def sample_mean_z(face: object) -> float:
    from openretop.cad_kernel.surfacing import sample_face

    return float(sample_face(face, 20)[:, 2].mean())


if __name__ == "__main__":
    unittest.main()
