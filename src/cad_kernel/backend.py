"""App-facing CAD-kernel backend helpers."""

from __future__ import annotations

from functools import lru_cache

from cad_kernel.occ_backend import (
    build_loft_surface_with_backend,
    build_planar_face_with_backend,
    detect_cad_kernel_backend,
    import_cad_backend,
)
from cad_kernel.export_step import export_step
from cad_kernel.types import (
    CadBuildResult,
    CadCurveInput,
    CadKernelInfo,
    CadKernelUnavailableError,
    clean_cad_curve_points,
)


@lru_cache(maxsize=1)
def cad_kernel_info() -> CadKernelInfo:
    """Return cached optional CAD-kernel availability details."""

    return detect_cad_kernel_backend()


def is_cad_kernel_available() -> bool:
    """Return True when an isolated CAD kernel backend can be imported."""

    return bool(cad_kernel_info().available)


def cad_kernel_status() -> str:
    """Return a user-facing CAD-kernel availability message."""

    return cad_kernel_info().status


def require_cad_kernel() -> object:
    """Return the backend module or raise a clear availability error."""

    if not is_cad_kernel_available():
        raise CadKernelUnavailableError(cad_kernel_status())
    return import_cad_backend()


def build_planar_face_from_curve(curve_input: CadCurveInput) -> CadBuildResult:
    """Build a CAD planar face from one closed curve input."""

    warnings: list[str] = []
    try:
        validation = _validated_planar_curve_input(curve_input)
    except ValueError as exc:
        return CadBuildResult(
            success=False,
            cad_object=None,
            reason=str(exc),
            warnings=warnings,
            metadata=_planar_face_metadata(
                curve_input,
                backend_name="validation",
            ),
        )

    warnings.extend(validation["warnings"])
    info = cad_kernel_info()
    metadata = _planar_face_metadata(
        curve_input,
        backend_name=info.backend_name,
        source_point_count=validation["source_point_count"],
        clean_point_count=validation["clean_point_count"],
        planarity_error=validation["planarity_error"],
        planarity_tolerance=validation["planarity_tolerance"],
    )

    if not info.available:
        return CadBuildResult(
            success=False,
            cad_object=None,
            reason=info.status,
            warnings=warnings,
            metadata=metadata,
        )

    try:
        backend_module = import_cad_backend()
        cad_object = build_planar_face_with_backend(
            backend_module,
            validation["points"],
        )
    except Exception as exc:
        return CadBuildResult(
            success=False,
            cad_object=None,
            reason=f"CAD kernel failed to build planar face: {exc}",
            warnings=warnings,
            metadata=metadata,
        )

    return CadBuildResult(
        success=True,
        cad_object=cad_object,
        reason="Planar BREP face built.",
        warnings=warnings,
        metadata=metadata,
    )


def build_loft_surface_from_curves(
    first_curve: CadCurveInput,
    second_curve: CadCurveInput,
) -> CadBuildResult:
    """Build a CAD loft surface from two curve inputs."""

    warnings: list[str] = []
    try:
        validation = _validated_loft_curve_inputs(first_curve, second_curve)
    except ValueError as exc:
        return CadBuildResult(
            success=False,
            cad_object=None,
            reason=str(exc),
            warnings=warnings,
            metadata=_loft_surface_metadata(
                first_curve,
                second_curve,
                backend_name="validation",
            ),
        )

    warnings.extend(validation["warnings"])
    info = cad_kernel_info()
    metadata = _loft_surface_metadata(
        first_curve,
        second_curve,
        backend_name=info.backend_name,
        source_point_counts=validation["source_point_counts"],
        clean_point_counts=validation["clean_point_counts"],
    )
    if warnings:
        metadata["warnings"] = list(warnings)

    if not info.available:
        return CadBuildResult(
            success=False,
            cad_object=None,
            reason=info.status,
            warnings=warnings,
            metadata=metadata,
        )

    try:
        backend_module = import_cad_backend()
        cad_object = build_loft_surface_with_backend(
            backend_module,
            validation["first_points"],
            validation["second_points"],
            closed=validation["closed"],
        )
    except Exception as exc:
        return CadBuildResult(
            success=False,
            cad_object=None,
            reason=f"CAD kernel failed to build loft surface: {exc}",
            warnings=warnings,
            metadata=metadata,
        )

    return CadBuildResult(
        success=True,
        cad_object=cad_object,
        reason="Loft BREP surface built.",
        warnings=warnings,
        metadata=metadata,
    )


def _validated_planar_curve_input(curve_input: CadCurveInput) -> dict[str, object]:
    if not bool(getattr(curve_input, "is_closed", False)):
        raise ValueError("Planar BREP face requires a closed curve.")

    raw_points = getattr(curve_input, "points", None)
    source_point_count = _source_point_count(curve_input, raw_points)
    try:
        points = clean_cad_curve_points(raw_points, closed=True)
    except ValueError as exc:
        raise ValueError(f"Planar BREP face input is invalid: {exc}") from exc

    np = _numpy()
    centroid = np.mean(points, axis=0)
    centered = points - centroid
    extent = _model_extent(points, getattr(curve_input, "metadata", {}))
    singular_values, normal = _best_fit_plane(centered)
    polygon_area = _polygon_area(points)
    area_tolerance = max((extent ** 2) * 1e-12, 1e-18)
    rank_tolerance = max(extent * 1e-9, 1e-12)
    if (
        len(singular_values) < 2
        or float(singular_values[1]) <= rank_tolerance
        or polygon_area <= area_tolerance
    ):
        raise ValueError(
            "Planar BREP face input is degenerate; curve points must span an area."
        )

    planarity_error = float(np.max(np.abs(centered @ normal)))
    planarity_tolerance = _planarity_tolerance(
        getattr(curve_input, "metadata", {}),
        extent,
    )
    if planarity_error > planarity_tolerance:
        raise ValueError(
            "Planar BREP face input is too non-planar "
            f"(error {planarity_error:.6g}, tolerance {planarity_tolerance:.6g})."
        )

    warnings: list[str] = []
    warning_tolerance = _planarity_warning_tolerance(
        getattr(curve_input, "metadata", {}),
        extent,
        planarity_tolerance,
    )
    if planarity_error > warning_tolerance:
        warnings.append(
            "Curve is slightly non-planar; using best-fit plane for planar face."
        )

    return {
        "points": points,
        "warnings": warnings,
        "source_point_count": source_point_count,
        "clean_point_count": int(len(points)),
        "planarity_error": planarity_error,
        "planarity_tolerance": planarity_tolerance,
    }


def _validated_loft_curve_inputs(
    first_curve: CadCurveInput,
    second_curve: CadCurveInput,
) -> dict[str, object]:
    first_closed = bool(getattr(first_curve, "is_closed", False))
    second_closed = bool(getattr(second_curve, "is_closed", False))
    if first_closed != second_closed:
        raise ValueError("Loft BREP surface requires both curves to be open or both closed.")

    try:
        first_points = clean_cad_curve_points(
            getattr(first_curve, "points", None),
            closed=first_closed,
        )
        second_points = clean_cad_curve_points(
            getattr(second_curve, "points", None),
            closed=second_closed,
        )
    except ValueError as exc:
        raise ValueError(f"Loft BREP surface input is invalid: {exc}") from exc

    if _curve_length(first_points, closed=first_closed) <= 1.0e-12:
        raise ValueError("Loft BREP surface first curve is degenerate.")
    if _curve_length(second_points, closed=second_closed) <= 1.0e-12:
        raise ValueError("Loft BREP surface second curve is degenerate.")

    warnings: list[str] = []
    if len(first_points) != len(second_points):
        warnings.append(
            "Loft source curves have different point counts; rebuild curves for better consistency."
        )

    return {
        "first_points": first_points,
        "second_points": second_points,
        "closed": first_closed,
        "warnings": warnings,
        "source_point_counts": (
            _source_point_count(first_curve, getattr(first_curve, "points", None)),
            _source_point_count(second_curve, getattr(second_curve, "points", None)),
        ),
        "clean_point_counts": (int(len(first_points)), int(len(second_points))),
    }


def _best_fit_plane(centered_points: object) -> tuple[object, object]:
    np = _numpy()
    try:
        _u, singular_values, vh = np.linalg.svd(centered_points, full_matrices=False)
    except np.linalg.LinAlgError as exc:
        raise ValueError("Planar BREP face input plane estimation failed.") from exc

    normal = vh[-1]
    normal_length = float(np.linalg.norm(normal))
    if normal_length <= 0.0 or not np.isfinite(normal_length):
        raise ValueError("Planar BREP face input plane normal is invalid.")
    return singular_values, normal / normal_length


def _polygon_area(points: object) -> float:
    np = _numpy()
    point_array = np.asarray(points, dtype=float).reshape((-1, 3))
    area_vector = np.zeros(3, dtype=float)
    for start, end in zip(point_array, np.roll(point_array, -1, axis=0)):
        area_vector += np.cross(start, end)
    return float(np.linalg.norm(area_vector) * 0.5)


def _curve_length(points: object, *, closed: bool) -> float:
    np = _numpy()
    point_array = np.asarray(points, dtype=float).reshape((-1, 3))
    if len(point_array) < 2:
        return 0.0
    path_points = (
        np.vstack((point_array, point_array[0]))
        if bool(closed)
        else point_array
    )
    return float(np.sum(np.linalg.norm(np.diff(path_points, axis=0), axis=1)))


def _model_extent(points: object, metadata: object) -> float:
    np = _numpy()
    metadata = metadata if isinstance(metadata, dict) else {}
    for key in ("model_extent", "bounding_box_size", "source_bounding_box_size"):
        value = _positive_finite_float(metadata.get(key))
        if value is not None:
            return value

    point_array = np.asarray(points, dtype=float).reshape((-1, 3))
    if len(point_array) == 0:
        return 1.0
    extent = float(np.max(np.ptp(point_array, axis=0)))
    return extent if extent > 0.0 and np.isfinite(extent) else 1.0


def _planarity_tolerance(metadata: object, extent: float) -> float:
    metadata = metadata if isinstance(metadata, dict) else {}
    explicit = _positive_finite_float(metadata.get("planarity_tolerance"))
    if explicit is not None:
        return explicit
    return max(float(extent) * 1e-2, 1e-5)


def _planarity_warning_tolerance(
    metadata: object,
    extent: float,
    strict_tolerance: float,
) -> float:
    metadata = metadata if isinstance(metadata, dict) else {}
    explicit = _positive_finite_float(metadata.get("planarity_warning_tolerance"))
    if explicit is not None:
        return min(explicit, strict_tolerance)
    return min(max(float(extent) * 1e-5, 1e-7), strict_tolerance)


def _source_point_count(curve_input: object, raw_points: object) -> int:
    metadata = getattr(curve_input, "metadata", {})
    if isinstance(metadata, dict):
        value = metadata.get("source_point_count")
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = -1
        if count >= 0:
            return count

    try:
        return int(len(raw_points))  # type: ignore[arg-type]
    except TypeError:
        return 0


def _planar_face_metadata(
    curve_input: object,
    *,
    backend_name: str,
    source_point_count: object | None = None,
    clean_point_count: object | None = None,
    planarity_error: object | None = None,
    planarity_tolerance: object | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "brep_type": "planar_face",
        "source_curve_id": str(getattr(curve_input, "curve_id", "") or ""),
        "source_curve_name": str(getattr(curve_input, "name", "") or ""),
        "backend": str(backend_name),
        "build_method": "closed_wire_planar_face",
    }
    if source_point_count is not None:
        metadata["source_point_count"] = int(source_point_count)
    if clean_point_count is not None:
        metadata["clean_point_count"] = int(clean_point_count)
    if planarity_error is not None:
        metadata["planarity_error"] = float(planarity_error)
    if planarity_tolerance is not None:
        metadata["planarity_tolerance"] = float(planarity_tolerance)
    return metadata


def _loft_surface_metadata(
    first_curve: object,
    second_curve: object,
    *,
    backend_name: str,
    source_point_counts: object | None = None,
    clean_point_counts: object | None = None,
) -> dict[str, object]:
    metadata: dict[str, object] = {
        "brep_type": "loft_surface",
        "source_curve_ids": [
            str(getattr(first_curve, "curve_id", "") or ""),
            str(getattr(second_curve, "curve_id", "") or ""),
        ],
        "source_curve_names": [
            str(getattr(first_curve, "name", "") or ""),
            str(getattr(second_curve, "name", "") or ""),
        ],
        "backend": str(backend_name),
        "build_method": "two_curve_loft",
        "closed": bool(getattr(first_curve, "is_closed", False))
        and bool(getattr(second_curve, "is_closed", False)),
    }
    if source_point_counts is not None:
        metadata["source_point_counts"] = [
            int(value) for value in source_point_counts
        ]
    if clean_point_counts is not None:
        metadata["clean_point_counts"] = [
            int(value) for value in clean_point_counts
        ]
    return metadata


def _positive_finite_float(value: object) -> float | None:
    np = _numpy()
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number > 0.0 and np.isfinite(number):
        return number
    return None


def _numpy() -> object:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("numpy is required for CAD planar face validation.") from exc
    return np
