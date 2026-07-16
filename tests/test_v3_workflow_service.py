from __future__ import annotations

from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from application.actions import CORE_ACTIONS
from application.commands import CommandRequest
from application.scene_ids import NODE_MESH
from application.state import MeshObjectState
from bootstrap import create_application
from mesh.triangle_mesh import TriangleMeshData


def _mesh() -> TriangleMeshData:
    return TriangleMeshData(
        vertices=np.asarray(
            [
                [0.0, 0.0, 0.0],
                [1.0, 0.0, 0.0],
                [0.0, 1.0, 0.0],
                [0.0, 0.0, 1.0],
            ],
            dtype=float,
        ),
        triangles=np.asarray(
            [[0, 1, 2], [0, 1, 3], [1, 2, 3], [0, 2, 3]], dtype=int
        ),
    )


def _mesh_object() -> MeshObjectState:
    mesh = _mesh()
    return MeshObjectState(
        source_mesh=mesh,
        display_mesh=mesh.copy(),
        file_path=None,
        name="Tetrahedron",
        origin=np.zeros(3),
        location=np.zeros(3),
        rotation=np.zeros(3),
        transform_matrix=np.identity(4),
    )


class V3WorkflowCoverageTests(unittest.TestCase):
    def test_every_core_action_is_registered_with_the_command_dispatcher(self) -> None:
        composition = create_application()
        expected = {definition.command_id for definition in CORE_ACTIONS}

        self.assertEqual(set(composition.commands.handler_ids), expected)
        for definition in CORE_ACTIONS:
            result = composition.commands.dispatch(
                CommandRequest(
                    command_id=definition.command_id,
                    action_id=definition.id,
                )
            )
            self.assertFalse(
                any("No handler is registered" in message for message in result.errors),
                definition.id,
            )

    def test_every_core_action_has_a_real_workflow_adapter(self) -> None:
        for definition in CORE_ACTIONS:
            composition = create_application()
            try:
                result = composition.workflow.dispatch(definition.id)
            except Exception as exc:  # pragma: no cover - gives a useful action ID on regression.
                self.fail(f"{definition.id} raised {type(exc).__name__}: {exc}")
            self.assertFalse(
                any("No V3 workflow adapter" in message for message in result.errors),
                definition.id,
            )

    def test_scene_edit_and_undo_flow_without_presentation_state(self) -> None:
        composition = create_application()
        composition.state.mesh_object = _mesh_object()

        self.assertTrue(composition.workflow.dispatch("scene.select_model").success)
        renamed = composition.workflow.dispatch(
            "scene.rename_selected", {"name": "Scan"}
        )
        self.assertTrue(renamed.success)
        self.assertEqual(composition.state.mesh_object.name, "Scan")
        self.assertTrue(composition.undo.can_undo)

        self.assertTrue(composition.workflow.dispatch("edit.undo").success)
        self.assertEqual(composition.state.mesh_object.name, "Tetrahedron")
        hidden = composition.workflow.dispatch("scene.toggle_visibility")
        self.assertTrue(hidden.success)
        self.assertFalse(composition.state.mesh_object.visible)
        self.assertEqual(composition.selection_controller.snapshot().ids, (NODE_MESH,))

    def test_section_manual_curve_and_region_flows_share_authoritative_state(self) -> None:
        composition = create_application()
        composition.state.mesh_object = _mesh_object()

        plane = composition.workflow.dispatch(
            "section.add_plane", {"axis": "Z", "offset": 0.25}
        )
        self.assertTrue(plane.success)
        section = composition.workflow.dispatch("section.compute")
        self.assertTrue(section.success, section.errors)
        self.assertTrue(composition.state.section_collection.results)

        curve_count = len(composition.state.curve_collection.curves)
        self.assertTrue(composition.workflow.dispatch("manual_curve.create").success)
        for point in ([0, 0, 0], [1, 0, 0], [0.5, 1, 0]):
            composition.manual_curve_controller.append_point(point)
        created = composition.workflow.dispatch("manual_curve.finish")
        self.assertTrue(created.success, created.errors)
        self.assertEqual(len(composition.state.curve_collection.curves), curve_count + 1)

        self.assertTrue(composition.workflow.dispatch("region.start").success)
        selected = composition.region_controller.select_seed(
            0, mesh=composition.state.mesh_object.display_mesh
        )
        self.assertTrue(selected.success, selected.errors)
        self.assertIsNotNone(composition.state.region_collection.active_region)


if __name__ == "__main__":
    unittest.main()
