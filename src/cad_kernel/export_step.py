"""STEP export boundary for CAD/BREP objects."""

from __future__ import annotations

import contextlib
import importlib
from pathlib import Path

from cad_kernel.types import StepExportResult
from geometry.units import DEFAULT_UNIT, get_unit

# OpenCascade STEP unit names for the units openRetop supports.
_STEP_UNIT_NAMES = {"mm": "MM", "cm": "CM", "m": "M", "in": "INCH"}


def export_step(
    cad_object: object,
    path: str | Path,
    units: str = DEFAULT_UNIT,
) -> StepExportResult:
    """Export a real CAD-kernel object to STEP.

    The model's numbers are in ``units``; the file declares that same unit, so
    a CAD package reading it sees the right physical size.
    """

    if cad_object is None:
        return StepExportResult(
            success=False,
            path=None,
            reason="No CAD object is available for STEP export.",
        )

    export_path = Path(path)
    if export_path.suffix.lower() not in {".step", ".stp"}:
        export_path = export_path.with_suffix(".step")
    try:
        export_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return StepExportResult(
            success=False,
            path=str(export_path),
            reason=f"Could not create STEP export folder: {exc}",
        )

    try:
        step_unit = _STEP_UNIT_NAMES[get_unit(units).code]
    except (ValueError, KeyError) as exc:
        return StepExportResult(success=False, path=str(export_path), reason=str(exc))

    try:
        with _step_unit_declared(step_unit):
            _export_step_object(cad_object, export_path, step_unit)
    except Exception as exc:
        return StepExportResult(
            success=False,
            path=str(export_path),
            reason=f"STEP export failed: {exc}",
        )

    try:
        if not export_path.exists() or export_path.stat().st_size <= 0:
            return StepExportResult(
                success=False,
                path=str(export_path),
                reason="STEP export failed: output file was not written.",
            )
    except OSError as exc:
        return StepExportResult(
            success=False,
            path=str(export_path),
            reason=f"STEP export failed: {exc}",
        )

    return StepExportResult(
        success=True,
        path=str(export_path),
        reason="STEP exported.",
    )


@contextlib.contextmanager
def _step_unit_declared(step_unit: str):
    """Make OpenCascade's STEP writer treat coordinates as ``step_unit`` and say so.

    Both statics are process-global, so the defaults are restored afterwards.
    """

    try:
        interface = importlib.import_module("OCP.Interface")
    except ImportError:
        yield  # non-OCP backend: the backend's own exporter decides the unit
        return
    statics = interface.Interface_Static
    names = ("xstep.cascade.unit", "write.step.unit")
    for name in names:
        statics.SetCVal_s(name, step_unit)
    try:
        yield
    finally:
        for name in names:
            statics.SetCVal_s(name, "MM")


def _export_step_object(cad_object: object, export_path: Path, step_unit: str) -> None:
    for method_name in (
        "export_step",
        "exportStep",
        "exportSTEP",
        "write_step",
        "writeStep",
        "writeSTEP",
    ):
        method = getattr(cad_object, method_name, None)
        if callable(method):
            try:
                # Newer CadQuery shapes set the STEP unit themselves from this
                # argument (default MM), overriding the process-wide statics.
                method(str(export_path), unit=step_unit)
            except TypeError:
                method(str(export_path))
            return

    module_name = str(type(cad_object).__module__)
    if module_name.startswith("cadquery"):
        _export_step_with_cadquery(cad_object, export_path, step_unit)
        return
    if module_name.startswith("OCP."):
        _export_step_with_opencascade("OCP", cad_object, export_path)
        return
    if module_name.startswith("OCC."):
        _export_step_with_opencascade("OCC.Core", cad_object, export_path)
        return

    # Some OpenCascade Python bindings expose shapes with short extension
    # module names, so try available backends before giving up.
    for module_prefix in ("OCP", "OCC.Core"):
        try:
            _export_step_with_opencascade(module_prefix, cad_object, export_path)
            return
        except ModuleNotFoundError:
            continue

    raise RuntimeError("CAD object does not expose a supported STEP export API.")


def _export_step_with_cadquery(cad_object: object, export_path: Path, step_unit: str) -> None:
    cadquery = importlib.import_module("cadquery")
    exporters = getattr(cadquery, "exporters", None)
    if exporters is not None and hasattr(exporters, "export"):
        try:
            exporters.export(cad_object, str(export_path), opt={"unit": step_unit})
        except TypeError:
            exporters.export(cad_object, str(export_path))
        return
    export_step_method = getattr(cad_object, "exportStep", None)
    if callable(export_step_method):
        export_step_method(str(export_path))
        return
    raise RuntimeError("CadQuery STEP export is unavailable.")


def _export_step_with_opencascade(
    module_prefix: str,
    cad_object: object,
    export_path: Path,
) -> None:
    step_module = importlib.import_module(f"{module_prefix}.STEPControl")
    ifselect_module = importlib.import_module(f"{module_prefix}.IFSelect")
    writer = step_module.STEPControl_Writer()
    transfer_status = writer.Transfer(cad_object, step_module.STEPControl_AsIs)
    ret_done = getattr(ifselect_module, "IFSelect_RetDone", 1)
    if transfer_status != ret_done and transfer_status is not True:
        raise RuntimeError("OpenCascade refused to transfer shape to STEP.")
    write_status = writer.Write(str(export_path))
    if write_status != ret_done and write_status is not True:
        raise RuntimeError("OpenCascade failed to write STEP file.")
