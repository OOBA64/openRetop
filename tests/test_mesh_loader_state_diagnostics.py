from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh.diagnostics import format_diagnostic_lines
from mesh.loader import load_mesh
from mesh.mesh_state import MeshState


class FakeBounds:
    def get_min_bound(self) -> tuple[float, float, float]:
        return (0.0, 0.0, 0.0)

    def get_max_bound(self) -> tuple[float, float, float]:
        return (1.0, 2.0, 3.0)

    def get_extent(self) -> tuple[float, float, float]:
        return (1.0, 2.0, 3.0)


class FakeMesh:
    vertices = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    triangles = [(0, 1, 2)]

    def get_axis_aligned_bounding_box(self) -> FakeBounds:
        return FakeBounds()

    def has_vertex_normals(self) -> bool:
        return True

    def has_triangle_normals(self) -> bool:
        return False

    def is_empty(self) -> bool:
        return False

    def is_watertight(self) -> bool:
        return False


class MeshLoaderStateDiagnosticsTests(unittest.TestCase):
    def test_loader_rejects_missing_paths_cleanly(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_mesh("missing-model.stl")

    def test_loader_rejects_unsupported_extensions_before_importing_open3d(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            mesh_path = Path(temp_dir) / "model.txt"
            mesh_path.write_text("not a mesh", encoding="utf-8")

            with self.assertRaises(ValueError):
                load_mesh(mesh_path)

    def test_mesh_state_and_diagnostics_capture_counts_and_bounds(self) -> None:
        state = MeshState.from_mesh(FakeMesh(), file_path="sample.stl")
        lines = format_diagnostic_lines(state)

        self.assertEqual(state.file_name, "sample.stl")
        self.assertEqual(state.vertex_count, 3)
        self.assertEqual(state.triangle_count, 1)
        self.assertEqual(state.bounding_box_extent, (1.0, 2.0, 3.0))
        self.assertTrue(any("Vertices: 3" in line for line in lines))
        self.assertTrue(any("Watertight: no" in line for line in lines))


if __name__ == "__main__":
    unittest.main()
