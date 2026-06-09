"""Load triangle meshes, print diagnostics, and show Open3D previews."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Sequence

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from geometry.curves import CurveFitResult, fit_section_polylines
from geometry.sections import SECTION_AXES, SectionPolyline, SectionResult, extract_section
from mesh.diagnostics import format_diagnostic_lines
from mesh.loader import LoadedMesh, load_mesh as load_mesh_with_metadata
from mesh.mesh_state import MeshState

if TYPE_CHECKING:
    import open3d as o3d


def _load_open3d():
    try:
        import open3d as o3d
    except ImportError as exc:
        raise SystemExit(
            "Open3D is required for mesh viewing. Install dependencies with: "
            "python -m pip install -r requirements.txt"
        ) from exc

    return o3d


def _load_numpy():
    try:
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "NumPy is required for section and normal visualization. It is installed "
            "with Open3D, or can be installed with: "
            "python -m pip install -r requirements.txt"
        ) from exc

    return np


def load_mesh(path: Path) -> o3d.geometry.TriangleMesh:
    """Compatibility wrapper that returns only the mesh object."""

    return load_mesh_with_metadata(path).mesh


def get_mesh_summary_lines(mesh_or_state: object) -> list[str]:
    """Return diagnostics for a mesh or already-built mesh state."""

    if isinstance(mesh_or_state, MeshState):
        state = mesh_or_state
    else:
        state = MeshState.from_mesh(mesh_or_state)

    return format_diagnostic_lines(state)


def print_mesh_summary(mesh_or_state: object) -> None:
    """Print core mesh diagnostics."""

    print("\n".join(get_mesh_summary_lines(mesh_or_state)))


def get_section_summary_lines(
    section_result: SectionResult | None,
    curve_results: Sequence[CurveFitResult] | None = None,
) -> list[str]:
    """Return display-ready section and curve-fit diagnostics."""

    if section_result is None:
        return ["Section", "  No section computed."]

    lines = [
        f"Section {section_result.axis} = {section_result.offset:.6g}",
        f"  Polylines: {len(section_result.polylines)}",
        f"  Intersected triangle segments: {section_result.segment_count}",
        f"  Section points: {section_result.point_count}",
    ]

    fit_results = list(curve_results or [])
    if fit_results:
        mean_error = sum(result.mean_error for result in fit_results) / len(fit_results)
        max_error = max(result.max_error for result in fit_results)
        fitted_point_count = sum(len(result.fitted_points) for result in fit_results)
        lines.extend(
            [
                f"  Fitted curves: {len(fit_results)}",
                f"  Fitted points: {fitted_point_count}",
                f"  Fit mean error: {mean_error:.6g}",
                f"  Fit max error: {max_error:.6g}",
            ]
        )
    else:
        lines.append("  Fitted curves: 0")

    return lines


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


def build_polyline_lines(
    polylines: Iterable[SectionPolyline | object],
    *,
    color: Sequence[float],
) -> o3d.geometry.LineSet | None:
    """Build an Open3D line overlay from section or curve polylines."""

    o3d = _load_open3d()
    np = _load_numpy()

    all_points: list[list[float]] = []
    all_lines: list[tuple[int, int]] = []

    for polyline in polylines:
        points = getattr(polyline, "points", polyline)
        points_array = np.asarray(points, dtype=float)
        if len(points_array) < 2:
            continue

        start_index = len(all_points)
        all_points.extend(points_array.tolist())
        all_lines.extend(
            (start_index + index, start_index + index + 1)
            for index in range(len(points_array) - 1)
        )

    if not all_points or not all_lines:
        return None

    line_set = o3d.geometry.LineSet()
    line_set.points = o3d.utility.Vector3dVector(np.asarray(all_points, dtype=float))
    line_set.lines = o3d.utility.Vector2iVector(np.asarray(all_lines, dtype=int))
    line_set.paint_uniform_color(list(color))

    return line_set


def show_mesh(
    mesh: o3d.geometry.TriangleMesh,
    *,
    show_normals: bool,
    normal_scale: float,
    section_result: SectionResult | None = None,
    curve_results: Sequence[CurveFitResult] | None = None,
    show_section: bool = True,
    show_fitted_curve: bool = True,
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

    if show_section and section_result is not None:
        section_lines = build_polyline_lines(
            section_result.polylines,
            color=[1.0, 0.32, 0.05],
        )
        if section_lines is not None:
            geometries.append(section_lines)

    if show_fitted_curve and curve_results:
        fitted_polylines = [result.fitted_points for result in curve_results]
        fitted_lines = build_polyline_lines(
            fitted_polylines,
            color=[0.1, 0.78, 0.28],
        )
        if fitted_lines is not None:
            geometries.append(fitted_lines)

    o3d.visualization.draw_geometries(
        geometries,
        window_name="openRetop Mesh Prototype",
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
        help="Only print diagnostics; do not open the 3D viewer.",
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
    parser.add_argument(
        "--section-axis",
        choices=SECTION_AXES,
        default="Z",
        help="Axis normal for the section plane.",
    )
    parser.add_argument(
        "--section-offset",
        type=float,
        default=0.0,
        help="Offset for the section plane along the selected axis.",
    )
    parser.add_argument(
        "--no-section",
        action="store_true",
        help="Skip section extraction and curve fitting.",
    )
    parser.add_argument(
        "--hide-section",
        action="store_true",
        help="Do not show the extracted section curve in the viewer.",
    )
    parser.add_argument(
        "--hide-fit",
        action="store_true",
        help="Do not show the smoothed fitted curve in the viewer.",
    )
    parser.add_argument(
        "--fit-iterations",
        type=int,
        default=2,
        help="Number of smoothing passes for the fitted curve prototype.",
    )
    return parser


def _build_section_and_fit(
    loaded: LoadedMesh,
    *,
    axis: str,
    offset: float,
    fit_iterations: int,
) -> tuple[SectionResult, list[CurveFitResult]]:
    section_result = extract_section(loaded.mesh, axis=axis, offset=offset)
    curve_results = fit_section_polylines(
        section_result.polylines,
        iterations=max(fit_iterations, 0),
    )
    return section_result, curve_results


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        loaded = load_mesh_with_metadata(args.mesh_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1

    state = MeshState.from_loaded_mesh(loaded)
    print_mesh_summary(state)

    section_result: SectionResult | None = None
    curve_results: list[CurveFitResult] = []
    if not args.no_section:
        section_result, curve_results = _build_section_and_fit(
            loaded,
            axis=args.section_axis,
            offset=args.section_offset,
            fit_iterations=args.fit_iterations,
        )
        print()
        print("\n".join(get_section_summary_lines(section_result, curve_results)))

    if not args.no_viewer:
        show_mesh(
            loaded.mesh,
            show_normals=not args.hide_normals,
            normal_scale=max(args.normal_scale, 0.0),
            section_result=section_result,
            curve_results=curve_results,
            show_section=not args.hide_section,
            show_fitted_curve=not args.hide_fit,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
