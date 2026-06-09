"""Load a triangle mesh and show it in a basic Open3D viewer."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    import open3d as o3d


SUPPORTED_EXTENSIONS = {".obj", ".ply", ".stl"}


def _load_open3d():
    try:
        import open3d as o3d
    except ImportError as exc:
        raise SystemExit(
            "Open3D is required for mesh import. Install dependencies with: "
            "python -m pip install -r thirdparty/requirements.txt"
        ) from exc

    return o3d


def _load_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "NumPy is required for normal visualization. It is installed with "
            "Open3D, or can be installed with: "
            "python -m pip install -r thirdparty/requirements.txt"
        ) from exc

    return np


def _format_vector(values: Sequence[float]) -> str:
    return ", ".join(f"{value:.6g}" for value in values)


def load_mesh(path: Path) -> o3d.geometry.TriangleMesh:
    """Load a mesh file and ensure normals are available when possible."""
    mesh_path = path.expanduser().resolve()

    if not mesh_path.exists():
        raise FileNotFoundError(f"Mesh file does not exist: {mesh_path}")

    if mesh_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise ValueError(
            f"Unsupported mesh format '{mesh_path.suffix}'. "
            f"Expected one of: {supported}"
        )

    o3d = _load_open3d()
    mesh = o3d.io.read_triangle_mesh(str(mesh_path))
    if mesh.is_empty():
        raise ValueError(f"Open3D could not read any mesh data from: {mesh_path}")

    if not mesh.has_vertex_normals():
        mesh.compute_vertex_normals()

    if not mesh.has_triangle_normals():
        mesh.compute_triangle_normals()

    return mesh


def print_mesh_summary(mesh: o3d.geometry.TriangleMesh) -> None:
    """Print core mesh counts and bounds."""
    vertex_count = len(mesh.vertices)
    triangle_count = len(mesh.triangles)
    bounding_box = mesh.get_axis_aligned_bounding_box()

    print("Mesh summary")
    print(f"  Vertices: {vertex_count}")
    print(f"  Triangles: {triangle_count}")
    print(f"  Bounding box min: {_format_vector(bounding_box.get_min_bound())}")
    print(f"  Bounding box max: {_format_vector(bounding_box.get_max_bound())}")
    print(f"  Bounding box extent: {_format_vector(bounding_box.get_extent())}")
    print(f"  Vertex normals: {'yes' if mesh.has_vertex_normals() else 'no'}")
    print(f"  Triangle normals: {'yes' if mesh.has_triangle_normals() else 'no'}")


def build_normal_lines(
    mesh: o3d.geometry.TriangleMesh, normal_scale: float
) -> o3d.geometry.LineSet | None:
    """Build a line overlay that shows vertex normals."""
    if not mesh.has_vertex_normals() or len(mesh.vertices) == 0:
        return None

    o3d = _load_open3d()
    np = _load_numpy()

    vertices = np.asarray(mesh.vertices)
    normals = np.asarray(mesh.vertex_normals)
    normal_length = max(float(mesh.get_axis_aligned_bounding_box().get_max_extent()), 1.0)
    normal_length *= normal_scale

    points = np.vstack((vertices, vertices + normals * normal_length))
    count = len(vertices)
    lines = np.column_stack((np.arange(count), np.arange(count) + count))

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(points)
    line_set.lines = o3d.utility.Vector2iVector(lines)
    line_set.paint_uniform_color([0.1, 0.45, 1.0])

    return line_set


def show_mesh(
    mesh: o3d.geometry.TriangleMesh, *, show_normals: bool, normal_scale: float
) -> None:
    """Open the mesh in Open3D's interactive viewer."""
    o3d = _load_open3d()

    if not mesh.has_vertex_colors():
        mesh.paint_uniform_color([0.72, 0.74, 0.78])

    geometries: list[o3d.geometry.Geometry] = [mesh]
    if show_normals:
        normal_lines = build_normal_lines(mesh, normal_scale)
        if normal_lines is not None:
            geometries.append(normal_lines)

    o3d.visualization.draw_geometries(
        geometries,
        window_name="openRetop Mesh Import Prototype",
        width=1280,
        height=800,
        mesh_show_back_face=True,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load an STL, OBJ, or PLY mesh and inspect it with Open3D."
    )
    parser.add_argument("mesh_path", type=Path, help="Path to an STL, OBJ, or PLY file.")
    parser.add_argument(
        "--no-viewer",
        action="store_true",
        help="Only print mesh statistics; do not open the 3D viewer.",
    )
    parser.add_argument(
        "--hide-normals",
        action="store_true",
        help="Do not show vertex normals in the viewer.",
    )
    parser.add_argument(
        "--normal-scale",
        type=float,
        default=0.02,
        help="Length of normal lines as a fraction of the mesh max extent.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        mesh = load_mesh(args.mesh_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    print_mesh_summary(mesh)

    if not args.no_viewer:
        show_mesh(
            mesh,
            show_normals=not args.hide_normals,
            normal_scale=max(args.normal_scale, 0.0),
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
