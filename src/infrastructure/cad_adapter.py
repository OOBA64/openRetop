"""Public, capability-accurate adapter for the optional CAD backend."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cad_kernel.backend import (
    build_loft_surface_from_cad_wires,
    build_loft_surface_from_curves,
    build_planar_face_from_cad_wire,
    build_planar_face_from_curve,
    cad_kernel_info,
)
from cad_kernel.curve_wire import build_cad_wire_from_curve
from cad_kernel.export_step import export_step
from cad_kernel.types import CadBuildResult, CadCurveInput, CadKernelInfo, StepExportResult
from cad_kernel.types import curve_points_from_stored_curve


@dataclass(frozen=True)
class CadCapabilities:
    available: bool
    backend_name: str
    wire: bool
    planar_face: bool
    loft: bool
    tessellation: bool
    step_export: bool
    trim: bool = False
    intersection: bool = False


class PublicCadAdapter:
    """Only exposes CAD operations implemented by the repository backend."""

    def __init__(self, info: CadKernelInfo | None = None) -> None:
        info = info or cad_kernel_info()
        self.info = info
        self.capabilities = CadCapabilities(
            available=bool(info.available),
            backend_name=str(info.backend_name),
            wire=bool(info.available),
            planar_face=bool(info.available),
            loft=bool(info.available),
            tessellation=bool(info.available),
            step_export=bool(info.available),
        )

    def build_wire(self, curve: object) -> CadBuildResult:
        if not self.capabilities.wire:
            return CadBuildResult(False, None, self.info.status)
        return build_cad_wire_from_curve(curve)

    def build_planar_face(self, curve: object) -> CadBuildResult:
        if not self.capabilities.planar_face:
            return CadBuildResult(False, None, self.info.status)
        if isinstance(curve, CadCurveInput):
            return build_planar_face_from_curve(curve)
        wire = self.build_wire(curve)
        if wire.success and wire.cad_object is not None:
            return build_planar_face_from_cad_wire(
                wire.cad_object,
                source_metadata=dict(wire.metadata),
            )
        return wire

    def build_loft(
        self,
        curves: list[object] | tuple[object, ...],
        options: object | None = None,
    ) -> CadBuildResult:
        if not self.capabilities.loft:
            return CadBuildResult(False, None, self.info.status)
        if len(curves) != 2:
            return CadBuildResult(False, None, "CAD loft requires exactly two source curves.")
        wires = [self.build_wire(curve) for curve in curves]
        option_value = lambda name, default=False: getattr(options, name, default)
        if all(item.success and item.cad_object is not None for item in wires):
            return build_loft_surface_from_cad_wires(
                [item.cad_object for item in wires],
                closed_profiles=bool(
                    option_value(
                        "closed_profiles",
                        bool(getattr(curves[0], "is_closed", False))
                        and bool(getattr(curves[1], "is_closed", False)),
                    )
                ),
                cap_start=bool(option_value("cap_start")),
                cap_end=bool(option_value("cap_end")),
                create_solid_if_closed=bool(option_value("create_solid_if_closed")),
                ruled=bool(option_value("ruled")),
            )
        try:
            curve_inputs = [curve_points_from_stored_curve(curve) for curve in curves]
        except ValueError as exc:
            return CadBuildResult(False, None, str(exc))
        return build_loft_surface_from_curves(curve_inputs[0], curve_inputs[1])

    def tessellate(self, cad_object: object) -> object:
        """Return the backend's public shape/mesh representation when present."""

        if not self.capabilities.tessellation:
            raise RuntimeError(self.info.status)
        for name in ("tessellate", "mesh", "toMesh"):
            method = getattr(cad_object, name, None)
            if callable(method):
                return method()
        raise RuntimeError("CAD backend does not expose tessellation.")

    def export_step(self, cad_object: object, path: str | Path) -> StepExportResult:
        if not self.capabilities.step_export:
            return StepExportResult(False, None, self.info.status)
        return export_step(cad_object, path)
