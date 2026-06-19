"""OpenCascade-family backend discovery.

CAD-kernel imports stay isolated in this module so the rest of the app can
launch even when OCP/pythonocc-core/CadQuery is not installed.
"""

from __future__ import annotations

import importlib
import importlib.util

from cad_kernel.types import CadKernelInfo, CadKernelUnavailableError


_BACKEND_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("OCP", "OCP"),
    ("pythonocc-core", "OCC.Core"),
    ("CadQuery", "cadquery"),
)


def detect_cad_kernel_backend() -> CadKernelInfo:
    """Return the first available OpenCascade-family backend."""

    for backend_name, module_name in _BACKEND_CANDIDATES:
        if _module_is_available(module_name):
            return CadKernelInfo(
                available=True,
                backend_name=backend_name,
                module_name=module_name,
                status=f"CAD kernel available: {backend_name}",
            )

    return CadKernelInfo(
        available=False,
        backend_name="unavailable",
        module_name=None,
        status="CAD kernel unavailable: install OCP/pythonocc-core to enable BREP export",
        detail="Checked optional backends: OCP, pythonocc-core, CadQuery.",
    )


def import_cad_backend() -> object:
    """Import and return the selected backend module, or raise a clear error."""

    info = detect_cad_kernel_backend()
    if not info.available or info.module_name is None:
        raise CadKernelUnavailableError(info.status)
    return importlib.import_module(info.module_name)


def build_planar_face_with_backend(backend_module: object, points: object) -> object:
    """Build a planar face object using the selected CAD backend."""

    builder = getattr(backend_module, "build_planar_face_from_points", None)
    if callable(builder):
        return builder(points)

    module_name = str(getattr(backend_module, "__name__", "")).strip()
    if module_name == "cadquery":
        return _build_planar_face_with_cadquery(backend_module, points)
    if module_name == "OCP" or module_name.startswith("OCP."):
        return _build_planar_face_with_opencascade("OCP", points)
    if module_name == "OCC.Core" or module_name.startswith("OCC."):
        return _build_planar_face_with_opencascade("OCC.Core", points)

    raise RuntimeError(f"Unsupported CAD backend: {module_name or type(backend_module).__name__}")


def build_loft_surface_with_backend(
    backend_module: object,
    first_points: object,
    second_points: object,
    *,
    closed: bool,
) -> object:
    """Build a loft surface object using the selected CAD backend."""

    builder = getattr(backend_module, "build_loft_surface_from_points", None)
    if callable(builder):
        return builder(first_points, second_points, closed=bool(closed))

    module_name = str(getattr(backend_module, "__name__", "")).strip()
    if module_name == "cadquery":
        return _build_loft_surface_with_cadquery(
            backend_module,
            first_points,
            second_points,
            closed=bool(closed),
        )
    if module_name == "OCP" or module_name.startswith("OCP."):
        return _build_loft_surface_with_opencascade(
            "OCP",
            first_points,
            second_points,
            closed=bool(closed),
        )
    if module_name == "OCC.Core" or module_name.startswith("OCC."):
        return _build_loft_surface_with_opencascade(
            "OCC.Core",
            first_points,
            second_points,
            closed=bool(closed),
        )

    raise RuntimeError(f"Unsupported CAD backend: {module_name or type(backend_module).__name__}")


def _module_is_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _build_planar_face_with_opencascade(module_prefix: str, points: object) -> object:
    np = _numpy()
    point_array = np.asarray(points, dtype=float).reshape((-1, 3))
    gp_module = importlib.import_module(f"{module_prefix}.gp")
    brep_module = importlib.import_module(f"{module_prefix}.BRepBuilderAPI")

    polygon = _opencascade_polygon_wire(gp_module, brep_module, point_array, close=True)
    face_builder = _make_opencascade_face_builder(
        brep_module.BRepBuilderAPI_MakeFace,
        polygon,
    )
    if hasattr(face_builder, "IsDone") and not bool(face_builder.IsDone()):
        raise RuntimeError("CAD planar face construction failed.")
    return face_builder.Face()


def _opencascade_polygon_wire(
    gp_module: object,
    brep_module: object,
    point_array: object,
    *,
    close: bool,
) -> object:
    polygon = brep_module.BRepBuilderAPI_MakePolygon()
    for point in point_array:
        polygon.Add(
            gp_module.gp_Pnt(
                float(point[0]),
                float(point[1]),
                float(point[2]),
            )
        )
    if close:
        polygon.Close()
    if hasattr(polygon, "IsDone") and not bool(polygon.IsDone()):
        raise RuntimeError("CAD wire construction failed.")
    return polygon.Wire()


def _make_opencascade_face_builder(face_builder_type: object, wire: object) -> object:
    try:
        return face_builder_type(wire, True)
    except TypeError:
        return face_builder_type(wire)


def _build_planar_face_with_cadquery(cadquery_module: object, points: object) -> object:
    np = _numpy()
    point_array = np.asarray(points, dtype=float).reshape((-1, 3))
    wire = _cadquery_polygon_wire(cadquery_module, point_array, close=True)
    return cadquery_module.Face.makeFromWires(wire)


def _build_loft_surface_with_opencascade(
    module_prefix: str,
    first_points: object,
    second_points: object,
    *,
    closed: bool,
) -> object:
    np = _numpy()
    first_array = np.asarray(first_points, dtype=float).reshape((-1, 3))
    second_array = np.asarray(second_points, dtype=float).reshape((-1, 3))
    gp_module = importlib.import_module(f"{module_prefix}.gp")
    brep_module = importlib.import_module(f"{module_prefix}.BRepBuilderAPI")
    loft_module = importlib.import_module(f"{module_prefix}.BRepOffsetAPI")

    first_wire = _opencascade_polygon_wire(
        gp_module,
        brep_module,
        first_array,
        close=bool(closed),
    )
    second_wire = _opencascade_polygon_wire(
        gp_module,
        brep_module,
        second_array,
        close=bool(closed),
    )
    loft = loft_module.BRepOffsetAPI_ThruSections(False, True, 1.0e-6)
    if hasattr(loft, "CheckCompatibility"):
        loft.CheckCompatibility(False)
    loft.AddWire(first_wire)
    loft.AddWire(second_wire)
    loft.Build()
    if hasattr(loft, "IsDone") and not bool(loft.IsDone()):
        raise RuntimeError("CAD loft construction failed.")
    return loft.Shape()


def _build_loft_surface_with_cadquery(
    cadquery_module: object,
    first_points: object,
    second_points: object,
    *,
    closed: bool,
) -> object:
    np = _numpy()
    first_array = np.asarray(first_points, dtype=float).reshape((-1, 3))
    second_array = np.asarray(second_points, dtype=float).reshape((-1, 3))
    first_wire = _cadquery_polygon_wire(cadquery_module, first_array, close=bool(closed))
    second_wire = _cadquery_polygon_wire(cadquery_module, second_array, close=bool(closed))
    solid_type = getattr(cadquery_module, "Solid", None)
    if solid_type is not None and hasattr(solid_type, "makeLoft"):
        return solid_type.makeLoft([first_wire, second_wire], ruled=True)
    shell_type = getattr(cadquery_module, "Shell", None)
    if shell_type is not None and hasattr(shell_type, "makeLoft"):
        return shell_type.makeLoft([first_wire, second_wire], ruled=True)
    raise RuntimeError("CadQuery loft construction is unavailable.")


def _cadquery_polygon_wire(
    cadquery_module: object,
    point_array: object,
    *,
    close: bool,
) -> object:
    vectors = [
        cadquery_module.Vector(
            float(point[0]),
            float(point[1]),
            float(point[2]),
        )
        for point in point_array
    ]
    return cadquery_module.Wire.makePolygon(vectors, close=bool(close))


def _numpy() -> object:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("numpy is required for CAD planar face construction.") from exc
    return np
