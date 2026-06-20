"""OpenCascade-family backend discovery.

CAD-kernel imports stay isolated in this module so the rest of the app can
launch even when OCP/pythonocc-core/CadQuery is not installed.
"""

from __future__ import annotations

import importlib
import importlib.util

from cad_kernel.types import CadKernelInfo, CadKernelUnavailableError


_BACKEND_CANDIDATES: tuple[tuple[str, str], ...] = (
    ("CadQuery", "cadquery"),
    ("OCP", "OCP"),
    ("pythonocc-core", "OCC.Core"),
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
        status="CAD kernel unavailable: install OCP/pythonocc-core or CadQuery to enable BREP export",
        detail="Checked optional backends: CadQuery, OCP, pythonocc-core.",
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


def build_planar_face_from_wire_with_backend(
    backend_module: object,
    wire: object,
) -> object:
    builder = getattr(backend_module, "build_planar_face_from_wire", None)
    if callable(builder):
        return builder(wire)
    module_name = str(getattr(backend_module, "__name__", "")).strip()
    if module_name == "cadquery":
        return backend_module.Face.makeFromWires(wire)
    if module_name == "OCP" or module_name.startswith("OCP."):
        brep_module = importlib.import_module("OCP.BRepBuilderAPI")
        return _make_opencascade_face_builder(brep_module.BRepBuilderAPI_MakeFace, wire).Face()
    if module_name == "OCC.Core" or module_name.startswith("OCC."):
        brep_module = importlib.import_module("OCC.Core.BRepBuilderAPI")
        return _make_opencascade_face_builder(brep_module.BRepBuilderAPI_MakeFace, wire).Face()
    raise RuntimeError(f"Unsupported CAD backend: {module_name or type(backend_module).__name__}")


def build_loft_from_wires_with_backend(
    backend_module: object,
    wires: list[object],
    *,
    closed_profiles: bool,
    cap_start: bool,
    cap_end: bool,
    create_solid_if_closed: bool,
    ruled: bool,
) -> tuple[object, dict[str, object], list[str]]:
    builder = getattr(backend_module, "build_loft_from_wires", None)
    if callable(builder):
        result = builder(
            wires,
            closed_profiles=bool(closed_profiles),
            cap_start=bool(cap_start),
            cap_end=bool(cap_end),
            create_solid_if_closed=bool(create_solid_if_closed),
            ruled=bool(ruled),
        )
        return result, {}, []
    module_name = str(getattr(backend_module, "__name__", "")).strip()
    if module_name == "cadquery":
        return _build_cadquery_loft_from_wires(
            backend_module,
            wires,
            closed_profiles=closed_profiles,
            cap_start=cap_start,
            cap_end=cap_end,
            create_solid_if_closed=create_solid_if_closed,
            ruled=ruled,
        )
    if module_name == "OCP" or module_name.startswith("OCP."):
        return _build_opencascade_loft_from_wires(
            "OCP",
            wires,
            closed_profiles=closed_profiles,
            cap_start=cap_start,
            cap_end=cap_end,
            create_solid_if_closed=create_solid_if_closed,
            ruled=ruled,
        )
    if module_name == "OCC.Core" or module_name.startswith("OCC."):
        return _build_opencascade_loft_from_wires(
            "OCC.Core",
            wires,
            closed_profiles=closed_profiles,
            cap_start=cap_start,
            cap_end=cap_end,
            create_solid_if_closed=create_solid_if_closed,
            ruled=ruled,
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


def _build_cadquery_loft_from_wires(
    cadquery: object,
    wires: list[object],
    *,
    closed_profiles: bool,
    cap_start: bool,
    cap_end: bool,
    create_solid_if_closed: bool,
    ruled: bool,
) -> tuple[object, dict[str, object], list[str]]:
    warnings: list[str] = []
    wants_solid = bool(
        closed_profiles and create_solid_if_closed and cap_start and cap_end
    )
    if wants_solid and hasattr(cadquery, "Solid") and hasattr(cadquery.Solid, "makeLoft"):
        shape = cadquery.Solid.makeLoft(wires, ruled=bool(ruled))
        return shape, {"loft_result_type": "solid", "caps_included": True}, warnings

    shell_type = getattr(cadquery, "Shell", None)
    if shell_type is not None and hasattr(shell_type, "makeLoft"):
        loft_shape = shell_type.makeLoft(wires, ruled=bool(ruled))
    elif hasattr(cadquery, "Solid") and hasattr(cadquery.Solid, "makeLoft"):
        loft_shape = cadquery.Solid.makeLoft(wires, ruled=bool(ruled))
    else:
        raise RuntimeError("CadQuery loft construction from wires is unavailable.")

    cap_shapes: list[object] = []
    if closed_profiles and cap_start:
        cap_shapes.append(cadquery.Face.makeFromWires(wires[0]))
    if closed_profiles and cap_end:
        cap_shapes.append(cadquery.Face.makeFromWires(wires[-1]))
    if cap_shapes:
        compound_type = getattr(cadquery, "Compound", None)
        if compound_type is not None and hasattr(compound_type, "makeCompound"):
            shape = compound_type.makeCompound([loft_shape, *cap_shapes])
            return shape, {
                "loft_result_type": "closed_loft_with_caps_compound",
                "caps_included": True,
                "cap_face_count": len(cap_shapes),
            }, warnings
        warnings.append("Loft caps could not be grouped by this CadQuery version.")
    return loft_shape, {
        "loft_result_type": "closed_shell" if closed_profiles else "open_sheet",
        "caps_included": False,
        "cap_face_count": 0,
    }, warnings


def _build_opencascade_loft_from_wires(
    module_prefix: str,
    wires: list[object],
    *,
    closed_profiles: bool,
    cap_start: bool,
    cap_end: bool,
    create_solid_if_closed: bool,
    ruled: bool,
) -> tuple[object, dict[str, object], list[str]]:
    loft_module = importlib.import_module(f"{module_prefix}.BRepOffsetAPI")
    wants_solid = bool(
        closed_profiles and create_solid_if_closed and cap_start and cap_end
    )
    loft = loft_module.BRepOffsetAPI_ThruSections(wants_solid, bool(ruled), 1.0e-6)
    if hasattr(loft, "CheckCompatibility"):
        loft.CheckCompatibility(False)
    for wire in wires:
        loft.AddWire(wire)
    loft.Build()
    if hasattr(loft, "IsDone") and not bool(loft.IsDone()):
        raise RuntimeError("CAD loft construction failed.")
    loft_shape = loft.Shape()
    if wants_solid:
        return loft_shape, {"loft_result_type": "solid", "caps_included": True}, []

    cap_shapes: list[object] = []
    if closed_profiles and (cap_start or cap_end):
        brep_module = importlib.import_module(f"{module_prefix}.BRepBuilderAPI")
        if cap_start:
            cap_shapes.append(
                _make_opencascade_face_builder(
                    brep_module.BRepBuilderAPI_MakeFace,
                    wires[0],
                ).Face()
            )
        if cap_end:
            cap_shapes.append(
                _make_opencascade_face_builder(
                    brep_module.BRepBuilderAPI_MakeFace,
                    wires[-1],
                ).Face()
            )
    if cap_shapes:
        try:
            topo_module = importlib.import_module(f"{module_prefix}.TopoDS")
            builder_module = importlib.import_module(f"{module_prefix}.BRep")
            compound = topo_module.TopoDS_Compound()
            builder = builder_module.BRep_Builder()
            builder.MakeCompound(compound)
            builder.Add(compound, loft_shape)
            for cap in cap_shapes:
                builder.Add(compound, cap)
            return compound, {
                "loft_result_type": "closed_loft_with_caps_compound",
                "caps_included": True,
                "cap_face_count": len(cap_shapes),
            }, []
        except (ImportError, AttributeError, TypeError):
            return loft_shape, {
                "loft_result_type": "closed_shell",
                "caps_included": False,
                "cap_face_count": 0,
            }, ["Loft caps were built but could not be grouped by this backend."]
    return loft_shape, {
        "loft_result_type": "closed_shell" if closed_profiles else "open_sheet",
        "caps_included": False,
        "cap_face_count": 0,
    }, []


def _numpy() -> object:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("numpy is required for CAD planar face construction.") from exc
    return np
