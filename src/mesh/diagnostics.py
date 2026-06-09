"""Simple mesh diagnostics for status output and CLI summaries."""

from __future__ import annotations

from dataclasses import dataclass

from mesh.mesh_state import MeshState, Vector3


@dataclass(frozen=True)
class MeshDiagnostics:
    vertex_count: int
    triangle_count: int
    bounding_box_min: Vector3
    bounding_box_max: Vector3
    bounding_box_extent: Vector3
    approximate_size: float
    is_empty: bool
    has_vertex_normals: bool
    has_triangle_normals: bool
    normals_computed: bool
    watertight: bool | None


def _format_vector(values: Vector3) -> str:
    return ", ".join(f"{value:.6g}" for value in values)


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def _get_watertight_status(state: MeshState) -> bool | None:
    if state.mesh is None:
        return None

    is_watertight = getattr(state.mesh, "is_watertight", None)
    if not callable(is_watertight):
        return None

    try:
        return bool(is_watertight())
    except RuntimeError:
        return None


def diagnose_mesh(state: MeshState) -> MeshDiagnostics:
    """Return basic diagnostics for the loaded mesh state."""

    is_empty = state.vertex_count == 0 or state.triangle_count == 0
    if state.mesh is not None and hasattr(state.mesh, "is_empty"):
        is_empty = bool(state.mesh.is_empty())

    return MeshDiagnostics(
        vertex_count=state.vertex_count,
        triangle_count=state.triangle_count,
        bounding_box_min=state.bounding_box_min,
        bounding_box_max=state.bounding_box_max,
        bounding_box_extent=state.bounding_box_extent,
        approximate_size=state.approximate_size,
        is_empty=is_empty,
        has_vertex_normals=state.has_vertex_normals,
        has_triangle_normals=state.has_triangle_normals,
        normals_computed=state.normals_computed,
        watertight=_get_watertight_status(state),
    )


def format_diagnostic_lines(state: MeshState) -> list[str]:
    """Return display-ready diagnostics lines."""

    diagnostics = diagnose_mesh(state)
    if diagnostics.watertight is None:
        watertight = "unsupported"
    else:
        watertight = _yes_no(diagnostics.watertight)

    return [
        "Mesh diagnostics",
        f"  Model name: {state.file_name or '(unnamed mesh)'}",
        f"  Vertices: {diagnostics.vertex_count}",
        f"  Triangles: {diagnostics.triangle_count}",
        f"  Bounding box min: {_format_vector(diagnostics.bounding_box_min)}",
        f"  Bounding box max: {_format_vector(diagnostics.bounding_box_max)}",
        f"  Bounding box size: {_format_vector(diagnostics.bounding_box_extent)}",
        f"  Approx. model size: {diagnostics.approximate_size:.6g}",
        f"  Empty mesh: {_yes_no(diagnostics.is_empty)}",
        (
            "  Normals: "
            f"vertex={_yes_no(diagnostics.has_vertex_normals)}, "
            f"triangle={_yes_no(diagnostics.has_triangle_normals)}, "
            f"computed={_yes_no(diagnostics.normals_computed)}"
        ),
        f"  Watertight: {watertight}",
    ]
