"""Run representative cached VTK mesh-query benchmarks.

Usage:
    python benchmarks/benchmark_mesh_queries.py
    python benchmarks/benchmark_mesh_queries.py --quick
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mesh.query_service import MeshQueryService
from mesh.triangle_mesh import TriangleMeshData


def _grid_mesh(target_triangle_count: int) -> TriangleMeshData:
    side = max(int(np.ceil(np.sqrt(target_triangle_count / 2.0))) + 1, 2)
    coordinates = np.linspace(0.0, 1.0, side)
    x_values, y_values = np.meshgrid(coordinates, coordinates, indexing="xy")
    vertices = np.column_stack(
        (x_values.ravel(), y_values.ravel(), np.zeros(side * side, dtype=float))
    )
    first = np.arange((side - 1) * (side - 1), dtype=np.int64)
    row = first // (side - 1)
    column = first % (side - 1)
    lower_left = row * side + column
    lower_right = lower_left + 1
    upper_left = lower_left + side
    upper_right = upper_left + 1
    triangles = np.vstack(
        (
            np.column_stack((lower_left, lower_right, upper_right)),
            np.column_stack((lower_left, upper_right, upper_left)),
        )
    )[:target_triangle_count]
    return TriangleMeshData(vertices=vertices, triangles=triangles)


def _query_points(count: int, *, seed: int) -> np.ndarray:
    generator = np.random.default_rng(seed)
    points = generator.random((count, 3))
    points[:, 2] = generator.uniform(-0.1, 0.1, count)
    return points


def run_case(triangle_count: int, point_count: int) -> dict[str, object]:
    mesh = _grid_mesh(triangle_count)
    points = _query_points(point_count, seed=triangle_count + point_count)
    service = MeshQueryService()
    first = service.query_closest_points(mesh, points, mesh_revision="benchmark-mesh")
    repeated = service.query_closest_points(mesh, points, mesh_revision="benchmark-mesh")
    return {
        "triangles": len(mesh.triangles),
        "points": point_count,
        "build_seconds": first.build_time_seconds,
        "first_query_seconds": first.query_time_seconds,
        "cached_query_seconds": repeated.query_time_seconds,
        "hits": repeated.hit_count,
        "misses": repeated.missed_count,
        "builds": service.diagnostics["index_build_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only the 10,000-triangle smoke benchmark.",
    )
    args = parser.parse_args()
    cases = [(10_000, 100)] if args.quick else [(10_000, 100), (100_000, 1_000)]

    print(
        "triangles points build_s first_query_s cached_query_s hits misses builds"
    )
    for triangle_count, point_count in cases:
        result = run_case(triangle_count, point_count)
        print(
            f"{result['triangles']:9d} {result['points']:6d} "
            f"{result['build_seconds']:.6f} {result['first_query_seconds']:.6f} "
            f"{result['cached_query_seconds']:.6f} {result['hits']:4d} "
            f"{result['misses']:6d} {result['builds']:6d}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
