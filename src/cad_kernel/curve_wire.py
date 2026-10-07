"""Build CAD wires from editable StoredCurve topology."""

from __future__ import annotations

import importlib

import numpy as np

from geometry.bspline import BSplineFit, fit_curve
from cad_kernel.occ_backend import detect_cad_kernel_backend, import_cad_backend
from cad_kernel.types import CadBuildResult, clean_cad_curve_points
from curves.manual_curve import (
    MANUAL_CURVE_METHOD_POLYLINE,
    manual_curve_segment_definitions,
    parse_manual_curve_metadata_v2,
)


def build_cad_wire_from_curve(curve: object) -> CadBuildResult:
    """Convert an editable curve into a line/spline CAD wire when possible."""

    metadata = getattr(curve, "metadata", {})
    metadata = metadata if isinstance(metadata, dict) else {}
    has_v2_topology = bool(
        metadata.get("manual_curve_version") == 2
        or isinstance(metadata.get("control_points_v2"), list)
        or isinstance(metadata.get("point_types"), list)
    )
    control_data = parse_manual_curve_metadata_v2(curve) if has_v2_topology else None
    is_closed = bool(getattr(curve, "is_closed", False) or metadata.get("closed"))
    cad_point_source = "manual_curve_v2"
    if control_data is not None:
        segments = manual_curve_segment_definitions(control_data)
        points = control_data.control_points
        is_closed = control_data.is_closed
    else:
        cad_point_source = "fitted_points_bspline"
        try:
            points = clean_cad_curve_points(
                getattr(curve, "fitted_points", None),
                closed=is_closed,
            )
        except ValueError as exc:
            return CadBuildResult(
                success=False,
                cad_object=None,
                reason=f"CAD wire input is invalid: {exc}",
                metadata={"cad_point_source": cad_point_source},
            )
        segments = _bspline_segments(points, closed=is_closed)

    if len(points) < (3 if is_closed else 2) or not segments:
        return CadBuildResult(
            success=False,
            cad_object=None,
            reason="CAD wire requires usable curve segments.",
            metadata={"cad_point_source": cad_point_source},
        )

    line_count = sum(str(segment.get("kind")) == "line" for segment in segments)
    spline_count = sum(str(segment.get("kind")) in ("spline", "bspline") for segment in segments)
    result_metadata: dict[str, object] = {
        "cad_wire_edge_count": int(line_count + spline_count),
        "cad_wire_line_edge_count": int(line_count),
        "cad_wire_spline_edge_count": int(spline_count),
        "cad_wire_closed": bool(is_closed),
        "cad_wire_build_method": "segment_aware_line_spline_wire",
        "cad_point_source": cad_point_source,
        "source_curve_id": str(getattr(curve, "id", "") or ""),
        "source_curve_name": str(getattr(curve, "name", "") or ""),
    }
    info = detect_cad_kernel_backend()
    result_metadata["backend"] = info.backend_name
    if not info.available:
        return CadBuildResult(
            success=False,
            cad_object=None,
            reason=info.status,
            metadata=result_metadata,
        )

    warnings: list[str] = []
    try:
        fallback_points = clean_cad_curve_points(
            getattr(curve, "fitted_points", points),
            closed=is_closed,
        )
    except ValueError:
        fallback_points = np.asarray(points, dtype=float).reshape((-1, 3))
    try:
        backend_module = import_cad_backend()
        wire, backend_warnings = _build_wire_with_backend(
            backend_module,
            points,
            segments,
            closed=is_closed,
            fallback_points=fallback_points,
        )
        warnings.extend(backend_warnings)
    except Exception as exc:
        return CadBuildResult(
            success=False,
            cad_object=None,
            reason=f"CAD kernel failed to build curve wire: {exc}",
            warnings=warnings,
            metadata=result_metadata,
        )

    if warnings:
        result_metadata["warnings"] = list(warnings)
        if any("sampled" in warning.lower() for warning in warnings):
            result_metadata["cad_wire_build_method"] = "sampled_curve_fallback_wire"
    return CadBuildResult(
        success=True,
        cad_object=wire,
        reason="CAD wire built from editable curve topology.",
        warnings=warnings,
        metadata=result_metadata,
    )


# Fit tolerance relative to the curve's own size. The input points already come
# from a fitted curve, so this only has to reproduce them closely.
_WIRE_FIT_RELATIVE_TOLERANCE = 1e-4


def _bspline_segments(points: np.ndarray, *, closed: bool) -> list[dict[str, object]]:
    """Approximate ``points`` with B-spline (and, at sharp corners, line) segments."""

    extent = float(np.max(points.max(axis=0) - points.min(axis=0)))
    fitted = fit_curve(
        points,
        tolerance=max(extent * _WIRE_FIT_RELATIVE_TOLERANCE, 1e-9),
        closed=closed,
    )
    segments: list[dict[str, object]] = []
    for piece in fitted.segments:
        if piece.degree == 1 and len(piece.poles) == 2:
            segments.append({"kind": "line", "points": piece.poles.copy(), "closed": False})
        else:
            segments.append(
                {
                    "kind": "bspline",
                    "fit": piece,
                    "points": piece.sample(max(16, 4 * len(piece.poles))),
                    "closed": bool(piece.periodic),
                }
            )
    return segments


def _build_wire_with_backend(
    backend_module: object,
    control_points: np.ndarray,
    segments: list[dict[str, object]],
    *,
    closed: bool,
    fallback_points: np.ndarray,
) -> tuple[object, list[str]]:
    builder = getattr(backend_module, "build_cad_wire_from_segments", None)
    if callable(builder):
        return builder(segments, closed=bool(closed)), []

    module_name = str(getattr(backend_module, "__name__", "")).strip()
    if module_name == "cadquery":
        return _cadquery_wire(backend_module, control_points, segments, closed=closed), []
    if module_name == "OCP" or module_name.startswith("OCP."):
        return _opencascade_wire("OCP", fallback_points, closed=closed), [
            "Used sampled curve fallback; inspect sharp corners."
        ] if any(segment.get("kind") == "spline" for segment in segments) else []
    if module_name == "OCC.Core" or module_name.startswith("OCC."):
        return _opencascade_wire("OCC.Core", fallback_points, closed=closed), [
            "Used sampled curve fallback; inspect sharp corners."
        ] if any(segment.get("kind") == "spline" for segment in segments) else []
    raise RuntimeError(f"Unsupported CAD backend: {module_name or type(backend_module).__name__}")


def _cadquery_wire(
    cadquery: object,
    control_points: np.ndarray,
    segments: list[dict[str, object]],
    *,
    closed: bool,
) -> object:
    if all(segment.get("kind") == "line" for segment in segments):
        polygon_points = [np.asarray(segment["points"], dtype=float)[0] for segment in segments]
        if not closed:
            polygon_points.append(np.asarray(segments[-1]["points"], dtype=float)[-1])
        vectors = [_cadquery_vector(cadquery, point) for point in polygon_points]
        return cadquery.Wire.makePolygon(vectors, close=bool(closed))

    edges: list[object] = []
    for segment in segments:
        if segment.get("kind") == "bspline":
            edges.append(_cadquery_bspline_edge(cadquery, segment["fit"]))
            continue
        segment_points = np.asarray(segment["points"], dtype=float).reshape((-1, 3))
        if segment.get("kind") == "line":
            edges.append(
                cadquery.Edge.makeLine(
                    _cadquery_vector(cadquery, segment_points[0]),
                    _cadquery_vector(cadquery, segment_points[-1]),
                )
            )
            continue
        spline_vectors = [_cadquery_vector(cadquery, point) for point in segment_points]
        periodic = bool(segment.get("closed"))
        try:
            edge = cadquery.Edge.makeSpline(spline_vectors, periodic=periodic)
        except TypeError:
            edge = cadquery.Edge.makeSpline(spline_vectors)
        edges.append(edge)
    assemble = getattr(cadquery.Wire, "assembleEdges", None)
    if callable(assemble):
        return assemble(edges)
    combined = cadquery.Wire.combine(edges)
    return combined[0] if isinstance(combined, list) and combined else combined


def _cadquery_bspline_edge(cadquery: object, fit: BSplineFit) -> object:
    """Exact NURBS edge (non-rational B-spline) built from the fitted poles and knots."""

    geom = importlib.import_module("OCP.Geom")
    gp = importlib.import_module("OCP.gp")
    tcolgp = importlib.import_module("OCP.TColgp")
    tcolstd = importlib.import_module("OCP.TColStd")
    builder = importlib.import_module("OCP.BRepBuilderAPI")

    pole_array = tcolgp.TColgp_Array1OfPnt(1, len(fit.poles))
    for index, pole in enumerate(fit.poles, start=1):
        pole_array.SetValue(index, gp.gp_Pnt(float(pole[0]), float(pole[1]), float(pole[2])))
    distinct, multiplicities = fit.occ_knots_and_multiplicities()
    knot_array = tcolstd.TColStd_Array1OfReal(1, len(distinct))
    mult_array = tcolstd.TColStd_Array1OfInteger(1, len(distinct))
    for index, (knot, multiplicity) in enumerate(zip(distinct, multiplicities), start=1):
        knot_array.SetValue(index, float(knot))
        mult_array.SetValue(index, int(multiplicity))
    curve = geom.Geom_BSplineCurve(
        pole_array, knot_array, mult_array, int(fit.degree), bool(fit.periodic)
    )
    return cadquery.Edge(builder.BRepBuilderAPI_MakeEdge(curve).Edge())


def _cadquery_vector(cadquery: object, point: np.ndarray) -> object:
    return cadquery.Vector(float(point[0]), float(point[1]), float(point[2]))


def _opencascade_wire(
    module_prefix: str,
    points: np.ndarray,
    *,
    closed: bool,
) -> object:
    gp_module = importlib.import_module(f"{module_prefix}.gp")
    brep_module = importlib.import_module(f"{module_prefix}.BRepBuilderAPI")
    polygon = brep_module.BRepBuilderAPI_MakePolygon()
    for point in points:
        polygon.Add(
            gp_module.gp_Pnt(float(point[0]), float(point[1]), float(point[2]))
        )
    if closed:
        polygon.Close()
    if hasattr(polygon, "IsDone") and not bool(polygon.IsDone()):
        raise RuntimeError("CAD wire construction failed.")
    return polygon.Wire()
