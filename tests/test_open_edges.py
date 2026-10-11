"""H-06: a trim that does not close says where and what to do; trimming again closes it.
H-03: a fitted plane covers the whole face it lies on, not only the part clicked.

A 10 mm cube scan with oversized planes on its faces: five trim into an open box whose four
open edges are drawn red; fitting the sixth and trimming again gives the closed solid."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

try:
    import cadquery  # noqa: F401
    import OCP  # noqa: F401

    HAVE_KERNEL = True
except ImportError:  # pragma: no cover
    HAVE_KERNEL = False

from test_surfacing_workflow import _composition, _install

FACES = (  # (normal, point) of each face of the cube [-5, 5]^3
    ((0, 0, 1), (0, 0, 5)),
    ((0, 0, -1), (0, 0, -5)),
    ((1, 0, 0), (5, 0, 0)),
    ((-1, 0, 0), (-5, 0, 0)),
    ((0, 1, 0), (0, 5, 0)),
    ((0, -1, 0), (0, -5, 0)),
)


def _cube_scan() -> tuple[np.ndarray, np.ndarray]:
    import trimesh

    mesh = trimesh.creation.box(extents=(10.0, 10.0, 10.0))
    for _ in range(4):
        mesh = mesh.subdivide()
    return np.asarray(mesh.vertices, dtype=float), np.asarray(mesh.faces, dtype=np.int64)


def _plane_entity(model, normal, point, half: float = 9.0):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    from openretop.cad_kernel import jobs
    from openretop.modeling.document import entity_from_result

    face = BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(*map(float, point)), gp_Dir(*map(float, normal))), -half, half, -half, half).Face()
    return model.add(entity_from_result(model, jobs.surface_result(face, kind="plane", rms=0.0, max_error=0.0), tool="fit_surface"))


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class KernelTests(unittest.TestCase):
    def _box_faces(self):
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox

        from openretop.cad_kernel import surfacing as S

        return S.faces_of(BRepPrimAPI_MakeBox(10.0, 10.0, 10.0).Shape())

    def test_the_open_edges_outline_the_missing_face(self) -> None:
        from openretop.cad_kernel import surfacing as S

        faces = self._box_faces()
        for missing in range(len(faces)):
            result = S.sew([face for index, face in enumerate(faces) if index != missing], tolerance=0.01)
            self.assertFalse(result.solid)
            free = S.free_edge_indices(result.shape)
            self.assertEqual(len(free), 4)
            self.assertEqual(len(free), result.free_edges)
            # they lie on the missing face's plane
            gone = S.sample_face(faces[missing], 20)
            normal = np.linalg.svd(gone - gone.mean(axis=0))[2][-1]
            for line in S.edge_polylines(result.shape, only=free):
                np.testing.assert_allclose((line - gone[0]) @ normal, 0.0, atol=1e-6)

    def test_a_solid_and_a_cylinder_seam_have_no_open_edges(self) -> None:
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

        from openretop.cad_kernel import surfacing as S

        self.assertEqual(S.sew(self._box_faces(), tolerance=0.01).free_edges, 0)
        side = next(face for face in S.faces_of(BRepPrimAPI_MakeCylinder(4.0, 10.0).Shape()) if S.face_area(face) > 200)
        self.assertEqual(len(S.free_edge_indices(side)), 2)  # the two rims, not the seam

    def test_a_lone_closed_face_sews_into_a_solid(self) -> None:
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeSphere

        from openretop.cad_kernel import jobs
        from openretop.cad_kernel import surfacing as S

        (sphere,) = S.faces_of(BRepPrimAPI_MakeSphere(5.0).Shape())
        result = jobs.sew([S.to_brep(sphere)])
        self.assertEqual(result["kind"], "solid")
        self.assertAlmostEqual(result["volume"], 4.0 / 3.0 * np.pi * 125.0, delta=0.5)


def _cube_breps() -> list[bytes]:
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeFace
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    from openretop.cad_kernel import surfacing as S

    return [
        S.to_brep(BRepBuilderAPI_MakeFace(gp_Pln(gp_Pnt(*map(float, point)), gp_Dir(*map(float, normal))), -7.0, 7.0, -7.0, 7.0).Face())
        for normal, point in FACES
    ]


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class TrimAgainTests(unittest.TestCase):
    def setUp(self) -> None:
        self.composition = _composition()
        _install(self.composition, *_cube_scan())
        self.model = self.composition.state.model
        self.planes = [_plane_entity(self.model, normal, point) for normal, point in FACES[:5]]

    def _trim(self):
        workflow = self.composition.workflow
        self.assertTrue(workflow.dispatch("model.trim", {}).success)
        self.assertTrue(workflow.dispatch("model.trim_compute", {}).success)
        result = workflow.dispatch("model.trim_apply", {"sew": True})
        self.assertTrue(result.success, result.errors)
        return result

    def test_an_open_box_says_where_and_trimming_again_closes_it(self) -> None:
        from openretop.application.guidance import Stage, build_guidance
        from openretop.viewer.modeling_scene import OPEN_EDGE_COLOR, ModelingSceneInput, modeling_items

        result = self._trim()
        self.assertTrue(result.status.startswith("Not closed yet: the red edges have no neighbouring face."), result.status)
        # the side planes run on past the open top with nothing to cut them: named
        self.assertIn("run on past the scan: a face next to them is probably missing", result.status)
        (shell,) = [entity for entity in self.model.visible() if entity.is_body]
        self.assertTrue(shell.not_closed)
        self.assertEqual(len(shell.open_edges), 4)
        # drawn red, and only once
        _faces, edges, _overlays = modeling_items(ModelingSceneInput(entities=(shell,)), None)
        red = next(item for item in edges if item.id == f"model-open:{shell.id}")
        plain = next(item for item in edges if item.id == f"model-edges:{shell.id}")
        self.assertEqual(len(red.polylines), 4)
        self.assertEqual(red.style.color, OPEN_EDGE_COLOR)
        self.assertEqual(len(plain.polylines), len(shell.edges) - 4)
        self.assertEqual(build_guidance(self.composition.state).stage, Stage.CLOSE)
        # exporting it works, and says it is not a solid
        with tempfile.TemporaryDirectory() as directory:
            exported = self.composition.modeling_controller.export(str(Path(directory) / "open.step"))
        self.assertTrue(exported.success)
        self.assertTrue(any("not closed" in warning for warning in exported.warnings), exported.warnings)
        # fit the missing face; Trim takes the open box's surfaces too, and closes it
        self.composition.modeling_controller.finish()
        sixth = _plane_entity(self.model, *FACES[5])
        self.assertTrue(self.composition.workflow.dispatch("model.trim", {}).success)
        session = self.composition.modeling_controller.session
        self.assertEqual(set(session.trim_sources), {plane.id for plane in self.planes} | {sixth.id})
        result = self._trim()
        self.assertTrue(result.status.startswith("Closed solid: volume 1,000.0"), result.status)
        self.assertFalse(self.model.get(shell.id).visible)  # replaced  # type: ignore[union-attr]
        (solid,) = [entity for entity in self.model.visible() if entity.is_body]
        self.assertEqual(solid.kind, "solid")
        self.assertEqual(build_guidance(self.composition.state).stage, Stage.EXPORT)
        # undo brings the open box back, red edges and all
        self.composition.workflow.dispatch("edit.undo", {})
        shell_again = self.model.get(shell.id)
        assert shell_again is not None
        self.assertTrue(shell_again.visible)
        self.assertEqual(len(shell_again.open_edges), 4)

    def test_trimming_other_surfaces_leaves_an_open_shell_alone(self) -> None:
        self._trim()
        (shell,) = [entity for entity in self.model.visible() if entity.is_body]
        self.composition.modeling_controller.finish()
        far = [_plane_entity(self.model, (0, 0, 1), (60, 0, 0)), _plane_entity(self.model, (1, 0, 0), (60, 0, 0))]
        self.model.selected_ids = [entity.id for entity in far]
        workflow = self.composition.workflow
        self.assertTrue(workflow.dispatch("model.trim", {}).success)
        self.assertTrue(workflow.dispatch("model.trim_compute", {}).success)
        session = self.composition.modeling_controller.session
        for index in range(len(session.trim_pieces)):  # no scan there: keep them all by hand
            if not session.trim_pieces[index]["keep"]:
                self.composition.modeling_controller.trim_toggle(index)
        self.assertTrue(workflow.dispatch("model.trim_apply", {"sew": True}).success)
        self.assertTrue(self.model.get(shell.id).visible)  # type: ignore[union-attr]

    def test_undo_clears_the_last_result_from_the_panel(self) -> None:
        self._trim()
        session = self.composition.modeling_controller.session
        self.assertTrue(session.trim_result.startswith("Not closed yet"))
        self.composition.workflow.dispatch("edit.undo", {})
        self.assertEqual(session.trim_result, "")

    def test_without_a_scan_no_surface_is_said_to_run_past_it(self) -> None:
        self.composition.state.mesh_object = None
        result = self._trim()
        self.assertTrue(result.status.startswith("Not closed yet"), result.status)
        self.assertNotIn("past the scan", result.status)

    def test_a_failed_sew_keeps_the_cut_lines(self) -> None:
        from unittest.mock import patch as mock_patch

        from openretop.cad_kernel.worker import KernelReply

        modeling = self.composition.modeling_controller
        workflow = self.composition.workflow
        self.assertTrue(workflow.dispatch("model.trim", {}).success)
        modeling.session.trim_cuts = [{"points": np.array([[-9.0, 0.0, 5.0], [9.0, 0.0, 5.0]]), "direction": np.array([0.0, 0.0, -1.0])}]
        self.assertTrue(workflow.dispatch("model.trim_compute", {}).success)
        call = modeling.worker.call

        def failing(name, *args, **kwargs):
            return KernelReply(False, None, "sewing crashed") if name == "sew" else call(name, *args, **kwargs)

        with mock_patch.object(modeling.worker, "call", side_effect=failing):
            self.assertFalse(workflow.dispatch("model.trim_apply", {"sew": True}).success)
        self.assertEqual(len(modeling.session.trim_cuts), 1)

    def test_the_plain_edges_rebuild_when_the_red_ones_come_and_go(self) -> None:
        from dataclasses import replace

        from openretop.viewer.modeling_scene import ModelingSceneInput, modeling_items

        self._trim()
        (shell,) = [entity for entity in self.model.visible() if entity.is_body]

        def plain(entity):
            _faces, edges, _overlays = modeling_items(ModelingSceneInput(entities=(entity,)), None)
            return next(item for item in edges if item.id.startswith("model-edges:"))

        shown, hidden = plain(shell), plain(replace(shell, visible=False))
        self.assertNotEqual(shown.revision, hidden.revision)
        self.assertNotEqual(len(shown.polylines), len(hidden.polylines))

    def test_the_open_edges_are_saved_with_the_project(self) -> None:
        from openretop.modeling.persistence import model_from_dict, model_to_dict

        self._trim()
        (shell,) = [entity for entity in self.model.visible() if entity.is_body]
        loaded, _warnings = model_from_dict(model_to_dict(self.model))
        self.assertEqual(loaded.get(shell.id).open_edges, shell.open_edges)  # type: ignore[union-attr]

    def test_the_trim_panel_says_it_and_shows_the_gaps(self) -> None:
        from PySide6.QtWidgets import QApplication

        from openretop.presentation.qt.main_window import OpenRetopV3Window
        from openretop.viewer.scene_types import CameraRequestKind

        QApplication.instance() or QApplication([])
        window = OpenRetopV3Window(self.composition)
        self.addCleanup(lambda: (window.set_project_dirty(False), window.close()))
        self.assertTrue(window._dispatch_application_action("model.trim"))
        self.assertTrue(window._dispatch_application_action("model.trim_compute"))
        self.assertTrue(window._dispatch_application_action("model.trim_apply", {"sew": True}))
        panel = window.surfacing_panel
        self.assertTrue(panel.trim_info.text().startswith("Not closed yet"), panel.trim_info.text())
        self.assertFalse(panel.trim_show_gaps.isHidden())
        requests = []
        refresh = window.refresh
        with patch.object(window, "refresh", side_effect=lambda: (requests.append(window._camera_request), refresh())):
            panel.trim_show_gaps.click()
        self.assertEqual(requests[0].kind, CameraRequestKind.FRAME_BOUNDS)
        (shell,) = [entity for entity in self.model.visible() if entity.is_body]
        rows = {field.id: field.value for field in window._surfacing_inspector_fields(f"model:{shell.id}") or ()}
        self.assertEqual(rows.get("model_kind"), "Shell (not closed)")
        self.assertEqual(rows.get("model_open"), 4)
        # renaming in the tree keeps only the name, not the words the row adds
        window._surfacing_tree_rename(f"model:{shell.id}", "Box (not closed)")
        self.assertEqual(self.model.get(shell.id).name, "Box")  # type: ignore[union-attr]


@unittest.skipUnless(HAVE_KERNEL, "OpenCASCADE / CadQuery not installed")
class PlaneCoversItsFaceTests(unittest.TestCase):
    def test_a_plane_fitted_to_a_small_patch_covers_the_whole_face(self) -> None:
        composition = _composition()
        vertices, triangles = _cube_scan()
        _install(composition, vertices, triangles)
        modeling = composition.modeling_controller
        self.assertTrue(composition.workflow.dispatch("model.fit_surface", {}).success)
        modeling.configure(fit_kind="plane")
        selection = modeling.selection()
        assert selection is not None
        selection.brush((5.0, 0.0, 0.0), 1.5)  # a small patch in the middle of the +x face
        self.assertLess(selection.count, len(triangles) // 30)
        result = composition.workflow.dispatch("model.fit_preview", {})
        self.assertTrue(result.success, result.errors)
        preview = modeling.session.preview  # type: ignore[union-attr]
        # the whole 10 x 10 face plus its margin, not the 3 mm patch plus a little
        self.assertGreater(preview["area"], 100.0)
        self.assertLess(preview["area"], 14.0 * 14.0)

    def test_grow_stops_where_triangles_are_not_allowed(self) -> None:
        from openretop.modeling import ScanSelection

        vertices, triangles = _cube_scan()
        selection = ScanSelection(vertices, triangles)
        centres = vertices[triangles].mean(axis=1)
        on_top = np.abs(centres[:, 2] - 5.0) < 1e-9
        selection.brush((0.0, 0.0, 5.0), 1.0)
        grown = selection.grow(on_top)
        np.testing.assert_array_equal(grown, on_top)
        self.assertLess(selection.count, int(np.count_nonzero(on_top)))  # the selection is untouched


if __name__ == "__main__":
    unittest.main()
