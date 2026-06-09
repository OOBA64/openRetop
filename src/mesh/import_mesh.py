"""Load triangle meshes and print diagnostics without starting a viewer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from geometry.curves import CurveFitResult, fit_section_polylines
from geometry.sections import SECTION_AXES, SectionResult, extract_section
from mesh.diagnostics import format_diagnostic_lines
from mesh.loader import LoadedMesh, load_mesh as load_mesh_with_metadata
from mesh.mesh_state import MeshState
from mesh.triangle_mesh import TriangleMeshData


def load_mesh(path: Path) -> TriangleMeshData:
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Load an STL, OBJ, or PLY mesh and print diagnostics."
    )
    parser.add_argument("mesh_path", type=Path, help="Path to an STL, OBJ, or PLY file.")
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
    return parser


def _build_section_and_fit(
    loaded: LoadedMesh,
    *,
    axis: str,
    offset: float,
) -> tuple[SectionResult, list[CurveFitResult]]:
    section_result = extract_section(loaded.mesh, axis=axis, offset=offset)
    curve_results = fit_section_polylines(section_result.polylines)
    return section_result, curve_results


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        loaded = load_mesh_with_metadata(args.mesh_path)
    except (FileNotFoundError, ValueError, SystemExit) as exc:
        print(f"Error: {exc}")
        return 1

    state = MeshState.from_loaded_mesh(loaded)
    print_mesh_summary(state)

    if not args.no_section:
        section_result, curve_results = _build_section_and_fit(
            loaded,
            axis=args.section_axis,
            offset=args.section_offset,
        )
        print()
        print("\n".join(get_section_summary_lines(section_result, curve_results)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
