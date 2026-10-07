from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh import loader
from mesh.adjacency import build_triangle_adjacency, cached_triangle_adjacency, grow_connected_region
from mesh.loader import MeshDependencyError, load_mesh
from mesh.triangle_mesh import TriangleMeshData
from mesh.weld import weld_vertices


def _export_box(directory: str, extension: str, extents=(2.0, 3.0, 4.0)) -> Path:
    path = Path(directory) / f"box{extension}"
    trimesh.creation.box(extents=extents).export(path)
    return path


class StlWeldingTests(unittest.TestCase):
    def test_stl_box_is_welded_into_shared_vertices(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loaded = load_mesh(_export_box(directory, ".stl"))

        self.assertEqual(len(loaded.mesh.triangles), 12)
        self.assertEqual(len(loaded.mesh.vertices), 8)
        self.assertEqual(loaded.metadata.vertex_count, 8)
        adjacency = build_triangle_adjacency(loaded.mesh)
        self.assertTrue(all(len(neighbors) == 3 for neighbors in adjacency))

    def test_stl_box_face_selects_exactly_two_triangles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            loaded = load_mesh(_export_box(directory, ".stl"))

        mesh = loaded.mesh
        normals = np.asarray(mesh.triangle_normals)
        for seed in range(len(mesh.triangles)):
            region = grow_connected_region(mesh, seed, threshold_degrees=20.0)
            self.assertEqual(len(region.triangle_indices), 2, f"seed {seed}")
            face_normals = normals[list(region.triangle_indices)]
            np.testing.assert_allclose(face_normals[0], face_normals[1], atol=1e-9)

    def test_tolerance_scales_with_mesh_size(self) -> None:
        # Two corners 1e-3 apart: noise on a 10 m part, a real gap on a 1 unit part.
        base = np.array(
            [[0, 0, 0], [1, 0, 0], [0, 1, 0], [1e-3, 0, 0], [1, 1, 0], [0, 1, 1]], float
        )
        triangles = np.array([[0, 1, 2], [3, 4, 5]])
        unit_scale = weld_vertices(base, triangles)
        large_scale = weld_vertices(base * 1.0e4, triangles)
        self.assertEqual(unit_scale.merged_vertex_count, 0)
        self.assertEqual(large_scale.merged_vertex_count, 0)  # gap scales too: 10 units
        close = base.copy()
        close[3] = [1e-9, 0, 0]
        self.assertEqual(weld_vertices(close, triangles).merged_vertex_count, 1)

    def test_exactly_coincident_corners_merge_at_any_scale(self) -> None:
        vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0], [1, 0, 0], [1, 1, 0]], float)
        for scale in (1e-3, 1.0, 1e5):
            result = weld_vertices(vertices * scale, np.array([[0, 1, 2], [3, 4, 5]]))
            self.assertEqual(len(result.vertices), 4)

    def test_degenerate_triangles_created_by_welding_are_dropped(self) -> None:
        vertices = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 0]], float)
        result = weld_vertices(vertices, np.array([[0, 1, 2], [0, 3, 1]]))
        self.assertEqual(len(result.triangles), 1)
        self.assertEqual(result.removed_triangle_count, 1)

    def test_obj_and_ply_still_load(self) -> None:
        for extension in (".obj", ".ply"):
            with tempfile.TemporaryDirectory() as directory:
                loaded = load_mesh(_export_box(directory, extension))
            self.assertEqual(len(loaded.mesh.triangles), 12, extension)
            self.assertEqual(len(loaded.mesh.vertices), 8, extension)


class LoaderBehaviourTests(unittest.TestCase):
    def test_missing_trimesh_raises_ordinary_exception_not_system_exit(self) -> None:
        real_import = __import__

        def fake_import(name, *args, **kwargs):
            if name == "trimesh":
                raise ImportError("no trimesh")
            return real_import(name, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            path = _export_box(directory, ".stl")
            with mock.patch("builtins.__import__", side_effect=fake_import):
                with self.assertRaises(MeshDependencyError) as caught:
                    load_mesh(path)
        self.assertNotIsInstance(caught.exception, SystemExit)
        self.assertIsInstance(caught.exception, RuntimeError)

    def test_corrupt_file_raises_value_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "broken.stl"
            path.write_bytes(b"solid broken\nnot really\n")
            with self.assertRaises(ValueError):
                load_mesh(path)

    def test_had_triangle_normals_reflects_the_file_not_lazy_computation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stl = load_mesh(_export_box(directory, ".stl"))
            ply = load_mesh(_export_box(directory, ".ply"))
        # Binary STL carries facet normals; a plain PLY box here does not.
        self.assertTrue(stl.metadata.had_triangle_normals)
        self.assertFalse(ply.metadata.had_triangle_normals)
        self.assertTrue(ply.metadata.computed_triangle_normals)
        self.assertTrue(ply.mesh.has_triangle_normals())
        self.assertTrue(ply.mesh.has_vertex_normals())


class AdjacencyCacheTests(unittest.TestCase):
    def _mesh(self) -> TriangleMeshData:
        vertices = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], float)
        return TriangleMeshData(vertices, np.array([[0, 1, 2], [0, 2, 3]]))

    def test_cache_is_released_with_the_mesh(self) -> None:
        mesh = self._mesh()
        cached_triangle_adjacency(mesh)
        self.assertFalse(hasattr(loader, "_ADJACENCY_CACHE"))
        import mesh.adjacency as adjacency_module

        self.assertFalse(hasattr(adjacency_module, "_ADJACENCY_CACHE"))

    def test_cache_not_shared_between_equal_shaped_meshes(self) -> None:
        first = self._mesh()
        cached_triangle_adjacency(first)
        second = self._mesh()
        second.triangles = np.array([[0, 1, 2], [1, 2, 3]])  # same counts, other topology
        self.assertEqual(cached_triangle_adjacency(second), build_triangle_adjacency(second))

    def test_cache_refreshes_when_triangles_are_replaced(self) -> None:
        mesh = self._mesh()
        before = cached_triangle_adjacency(mesh)
        mesh.triangles = np.array([[0, 1, 2], [0, 2, 3], [0, 3, 1]])
        after = cached_triangle_adjacency(mesh)
        self.assertEqual(len(before), 2)
        self.assertEqual(len(after), 3)

    def test_copy_does_not_alias_cache(self) -> None:
        mesh = self._mesh()
        first = cached_triangle_adjacency(mesh)
        clone = mesh.copy()
        self.assertEqual(cached_triangle_adjacency(clone), first)


if __name__ == "__main__":
    unittest.main()
