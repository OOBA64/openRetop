"""Optional CAD-kernel integration boundary."""

from cad_kernel.backend import (
    build_cad_wire_from_curve,
    build_loft_surface_from_cad_wires,
    build_loft_surface_from_curves,
    build_planar_face_from_cad_wire,
    build_planar_face_from_curve,
    cad_kernel_info,
    cad_kernel_status,
    export_step,
    is_cad_kernel_available,
    require_cad_kernel,
)
from cad_kernel.types import (
    CadBuildResult,
    CadCurveInput,
    CadKernelInfo,
    CadKernelUnavailableError,
    StepExportResult,
    clean_cad_curve_points,
    curve_points_from_stored_curve,
)

__all__ = [
    "CadBuildResult",
    "CadCurveInput",
    "CadKernelInfo",
    "CadKernelUnavailableError",
    "StepExportResult",
    "build_loft_surface_from_curves",
    "build_cad_wire_from_curve",
    "build_loft_surface_from_cad_wires",
    "build_planar_face_from_cad_wire",
    "build_planar_face_from_curve",
    "cad_kernel_info",
    "cad_kernel_status",
    "clean_cad_curve_points",
    "curve_points_from_stored_curve",
    "export_step",
    "is_cad_kernel_available",
    "require_cad_kernel",
]
