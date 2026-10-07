"""Public CAD-kernel types used by app-facing code."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class CadKernelInfo:
    """Availability and identity details for the optional CAD kernel."""

    available: bool
    backend_name: str
    module_name: str | None
    status: str
    detail: str = ""


class CadKernelUnavailableError(RuntimeError):
    """Raised when CAD/BREP work is requested without an available kernel."""


@dataclass
class CadBuildResult:
    success: bool
    cad_object: object | None
    reason: str
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass
class StepExportResult:
    success: bool
    path: str | None
    reason: str
    warnings: list[str] = field(default_factory=list)


@dataclass
class CadCurveInput:
    points: np.ndarray
    is_closed: bool
    name: str
    curve_id: str
    metadata: dict[str, object] = field(default_factory=dict)


def clean_cad_curve_points(points: object, closed: bool) -> np.ndarray:
    """Return finite 3D points suitable for CAD-kernel curve construction."""

    np = _numpy()
    point_array = _cad_point_array(points)
    _require_finite_points(point_array)

    cleaned = _remove_exact_duplicate_consecutive_points(point_array)
    if bool(closed) and len(cleaned) > 1 and np.array_equal(cleaned[0], cleaned[-1]):
        cleaned = cleaned[:-1].copy()

    minimum_count = 3 if bool(closed) else 2
    if len(cleaned) < minimum_count:
        shape = "Closed CAD curves" if bool(closed) else "CAD curves"
        raise ValueError(
            f"{shape} require at least {minimum_count} finite non-duplicate points."
        )

    return np.asarray(cleaned, dtype=float).reshape((-1, 3)).copy()


def curve_points_from_stored_curve(curve: object) -> CadCurveInput:
    """Build clean CAD input points from a StoredCurve-like object."""

    metadata = getattr(curve, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    curve_id = str(getattr(curve, "id", "") or "")
    curve_name = str(getattr(curve, "name", curve_id) or curve_id)
    is_closed = bool(getattr(curve, "is_closed", False) or metadata.get("closed"))

    try:
        point_source, raw_points = _cad_points_for_curve(curve, metadata)
        raw_point_count = len(_cad_point_array(raw_points))
        clean_points = clean_cad_curve_points(raw_points, is_closed)
    except ValueError as exc:
        label = curve_id or curve_name or "(unnamed)"
        raise ValueError(f"Curve {label} cannot be used for CAD: {exc}") from exc

    result_metadata: dict[str, object] = {
        "point_source": point_source,
        "source_point_count": int(raw_point_count),
        "clean_point_count": int(len(clean_points)),
        "removed_duplicate_point_count": int(raw_point_count - len(clean_points)),
    }
    if curve_id:
        result_metadata["source_curve_id"] = curve_id
    if curve_name:
        result_metadata["source_curve_name"] = curve_name

    return CadCurveInput(
        points=clean_points,
        is_closed=is_closed,
        name=curve_name,
        curve_id=curve_id,
        metadata=result_metadata,
    )


def _cad_points_for_curve(
    curve: object,
    metadata: dict[str, object],
) -> tuple[str, object]:
    requested_source = _requested_cad_point_source(metadata)
    if requested_source == "control_points":
        if "control_points" not in metadata:
            raise ValueError(
                "Curve requested control points for CAD but has no control_points metadata."
            )
        return ("control_points", metadata["control_points"])

    fitted_points = getattr(curve, "fitted_points", None)
    if fitted_points is not None:
        return ("fitted_points", fitted_points)

    if "control_points" in metadata:
        return ("control_points", metadata["control_points"])

    raise ValueError("Curve has no fitted_points or control_points for CAD.")


def _requested_cad_point_source(metadata: dict[str, object]) -> str:
    value = metadata.get("cad_point_source", metadata.get("cad_points_source", ""))
    token = str(value).strip().lower()
    if token in {"control", "control_point", "control_points"}:
        return "control_points"
    if token in {"fit", "fitted", "fitted_point", "fitted_points"}:
        return "fitted_points"
    if bool(metadata.get("cad_use_control_points")) or bool(
        metadata.get("use_control_points_for_cad")
    ):
        return "control_points"
    return "fitted_points"


def _cad_point_array(points: object) -> np.ndarray:
    np = _numpy()
    try:
        point_array = np.asarray(points, dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("CAD curve points must be numeric 3D points.") from exc

    if point_array.ndim != 2 or point_array.shape[1] != 3:
        raise ValueError("CAD curve points must be an Nx3 array.")
    return point_array.reshape((-1, 3))


def _require_finite_points(points: np.ndarray) -> None:
    np = _numpy()
    finite_mask = np.isfinite(points)
    if bool(np.all(finite_mask)):
        return

    bad_indices = np.argwhere(~finite_mask)
    point_index = int(bad_indices[0][0]) if len(bad_indices) else -1
    raise ValueError(
        f"CAD curve points must be finite; invalid value at point {point_index}."
    )


def _remove_exact_duplicate_consecutive_points(points: np.ndarray) -> np.ndarray:
    np = _numpy()
    if len(points) == 0:
        return np.zeros((0, 3), dtype=float)

    cleaned = [points[0]]
    for point in points[1:]:
        if not np.array_equal(point, cleaned[-1]):
            cleaned.append(point)
    return np.asarray(cleaned, dtype=float).reshape((-1, 3))


def _numpy() -> object:
    try:
        import numpy as np
    except ModuleNotFoundError as exc:
        raise RuntimeError("numpy is required for CAD curve point processing.") from exc
    return np
