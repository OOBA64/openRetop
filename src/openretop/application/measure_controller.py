"""Measure distances on the scan to verify that it came in at the right size.

Click two points on the mesh: the distance between them is reported in the project's
units, with its X/Y/Z components.  Measurements are a viewing aid: they are not saved with
the project and are not part of the undo history.

When the display mesh is a reduced proxy of a large scan, picked points are snapped onto
the full-resolution source mesh, so a measurement is as accurate as the scan itself.
"""

from __future__ import annotations

import math

import numpy as np

from openretop.application.controller_support import ControllerBase
from openretop.application.events import EventPublisher
from openretop.application.results import CommandResult
from openretop.application.state import AppState, Measurement
from openretop.mesh.query_service import MeshQueryService

MEASURE_TOOL_ID = "measure"
SNAP_FRACTION_OF_DIAGONAL = 0.02  # how far a click may be moved onto the source mesh


def format_length(value: float, units: str) -> str:
    """A length with sensible precision for its size, for example ``42.31 mm`` or ``1.666 in``."""

    if not math.isfinite(value):
        return f"-- {units}".strip()
    magnitude = abs(value)
    decimals = 0 if magnitude >= 1000.0 else 1 if magnitude >= 100.0 else 2 if magnitude >= 1.0 else 3
    if magnitude != 0.0 and magnitude < 0.001:
        text = f"{value:.3g}"
    else:
        text = f"{value:.{decimals}f}"
    return f"{text} {units}".strip()


def describe_measurement(measurement: Measurement, units: str) -> str:
    dx, dy, dz = (float(value) for value in measurement.delta)
    return (
        f"Distance {format_length(measurement.distance, units)}"
        f"  (dX {format_length(abs(dx), units)}, dY {format_length(abs(dy), units)}, dZ {format_length(abs(dz), units)})"
    )


class MeasureController(ControllerBase):
    def __init__(
        self,
        state: AppState,
        events: EventPublisher | None = None,
        *,
        mesh_query_service: MeshQueryService | None = None,
        transformed_mesh_provider: object | None = None,
    ) -> None:
        super().__init__(state, events)
        self._query = mesh_query_service
        self._transformed_mesh = transformed_mesh_provider  # callable returning the world-space source mesh
        self._snap_cache_key: object | None = None
        self._snap_mesh: object | None = None

    # -- state ------------------------------------------------------------------------

    @property
    def active(self) -> bool:
        return self.state.measure.active

    @property
    def measurements(self) -> tuple[Measurement, ...]:
        return tuple(self.state.measure.measurements)

    @property
    def pending(self) -> tuple[float, float, float] | None:
        return self.state.measure.pending

    @property
    def has_measurements(self) -> bool:
        return bool(self.state.measure.measurements) or self.state.measure.pending is not None

    # -- commands ---------------------------------------------------------------------

    def start(self) -> CommandResult:
        if self.state.mesh_object is None:
            return CommandResult.failure("Open a scan to measure.", status="No scan loaded")
        measure = self.state.measure
        measure.active = True
        measure.pending = None
        return CommandResult.ok(
            status="Measure: click two points on the scan. Esc finishes.",
            metadata={"tool": MEASURE_TOOL_ID},
        )

    def finish(self) -> CommandResult:
        """Leave the tool; a half-made measurement is dropped, finished ones stay on screen."""

        measure = self.state.measure
        was_active = measure.active
        measure.active = False
        measure.pending = None
        return CommandResult.ok(status="Measure tool closed" if was_active else "", changed=was_active)

    def cancel_pending(self) -> bool:
        """Drop the first point of an unfinished measurement; True if there was one."""

        measure = self.state.measure
        had = measure.pending is not None
        measure.pending = None
        return had

    def clear(self) -> CommandResult:
        measure = self.state.measure
        count = len(measure.measurements)
        measure.measurements.clear()
        measure.pending = None
        return CommandResult.ok(
            status="Measurements cleared" if count else "No measurements to clear",
            changed=bool(count),
        )

    def add_point(self, position: object | None) -> CommandResult:
        """Handle a click on the mesh at world ``position`` (None when the click missed it)."""

        measure = self.state.measure
        if not measure.active:
            return CommandResult.failure("The measure tool is not active.")
        point = _point(position)
        if point is None:
            return CommandResult.ok(status="Click on the scan to place a point.")
        point = self._snapped(point)
        units = self.state.units
        if measure.pending is None:
            measure.pending = point
            return CommandResult.ok(status="First point set. Click the second point (Esc cancels).", changed=True)
        measurement = Measurement(
            id=f"measurement-{len(measure.measurements) + 1}",
            start=measure.pending,
            end=point,
        )
        measure.measurements.append(measurement)
        measure.pending = None
        return CommandResult.ok(
            status=describe_measurement(measurement, units),
            changed=True,
            metadata={"distance": measurement.distance, "units": units, "measurement_id": measurement.id},
        )

    def describe_model_size(self) -> CommandResult:
        """Bounding-box size of the scan in project units, for a quick check against the real part."""

        mesh = self.state.mesh_object
        if mesh is None or mesh.source_bounds_min is None or mesh.source_bounds_max is None:
            return CommandResult.failure("Open a scan to see its size.", status="No scan loaded")
        scale = float(getattr(mesh, "scale", 1.0) or 1.0)
        size = (np.asarray(mesh.source_bounds_max, dtype=float) - np.asarray(mesh.source_bounds_min, dtype=float)) * abs(scale)
        diagonal = float(np.linalg.norm(size))
        units = self.state.units
        status = (
            f"Model size: {format_length(float(size[0]), units)} x {format_length(float(size[1]), units)} x "
            f"{format_length(float(size[2]), units)}  (diagonal {format_length(diagonal, units)})"
        )
        if self.state.units_assumed:
            status += ". Units were assumed: use File > Set Model Units if this looks wrong."
        return CommandResult.ok(status=status, metadata={"size": tuple(float(value) for value in size), "diagonal": diagonal})

    # -- snapping ---------------------------------------------------------------------

    def _snapped(self, point: tuple[float, float, float]) -> tuple[float, float, float]:
        mesh = self.state.mesh_object
        if (
            mesh is None
            or not getattr(mesh, "display_proxy_enabled", False)
            or self._query is None
            or self._transformed_mesh is None
        ):
            return point  # the display mesh is the source mesh: the picked point is already exact
        try:
            matrix = getattr(mesh, "transform_matrix", None)
            key = (id(mesh.source_mesh), None if matrix is None else tuple(np.asarray(matrix, dtype=float).reshape(-1)))
            if key != self._snap_cache_key or self._snap_mesh is None:
                self._snap_mesh = self._transformed_mesh()  # type: ignore[operator]
                self._snap_cache_key = key
            bounds = np.asarray(mesh.source_bounds_max, dtype=float) - np.asarray(mesh.source_bounds_min, dtype=float)
            tolerance = max(float(np.linalg.norm(bounds)) * SNAP_FRACTION_OF_DIAGONAL, 1e-9)
            result = self._query.query_closest_points(
                self._snap_mesh,  # type: ignore[arg-type]
                [point],
                mesh_revision=("measure", key),
                max_distance=tolerance,
                preserve_missed_points=True,
            )
            if bool(result.hit_mask[0]):
                snapped = _point(result.closest_points[0])
                if snapped is not None:
                    return snapped
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass
        return point


def _point(value: object | None) -> tuple[float, float, float] | None:
    if value is None:
        return None
    try:
        array = np.asarray(value, dtype=float).reshape(3)
    except (TypeError, ValueError):
        return None
    if not np.all(np.isfinite(array)):
        return None
    return (float(array[0]), float(array[1]), float(array[2]))


__all__ = (
    "MEASURE_TOOL_ID",
    "MeasureController",
    "describe_measurement",
    "format_length",
)
