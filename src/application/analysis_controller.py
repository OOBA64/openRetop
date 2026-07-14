"""UI-independent read-only analysis workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from analysis.deviation import DeviationResult, compute_point_deviation_to_mesh
from application.controller_support import ControllerBase
from application.events import StatusEvent, StatusLevel
from application.results import CommandResult
from application.state import AppState
from application.transform_math import (
    build_object_transform_matrix,
    transform_bounds,
)
from mesh.triangle_mesh import TriangleMeshData


class MeshIndexPort(Protocol):
    def get_index(
        self,
        mesh: TriangleMeshData,
        *,
        mesh_revision: object | None = None,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class AnalysisSnapshot:
    """Small immutable summary suitable for an analysis/presentation adapter."""

    mesh_name: str = ""
    source_vertex_count: int = 0
    source_triangle_count: int = 0
    display_vertex_count: int = 0
    display_triangle_count: int = 0
    display_proxy_enabled: bool = False
    minimum_bound: tuple[float, float, float] | None = None
    maximum_bound: tuple[float, float, float] | None = None
    curve_count: int = 0
    surface_count: int = 0
    brep_surface_count: int = 0
    active_region_id: str | None = None
    active_region_triangle_count: int = 0
    selected_item: str | None = None


class AnalysisController(ControllerBase):
    """Compute analysis through an injected shared mesh-query service."""

    def __init__(
        self,
        state: AppState,
        *,
        events=None,
        mesh_query_service: MeshIndexPort | None = None,
    ) -> None:
        super().__init__(state, events=events)
        self.mesh_query_service = mesh_query_service

    def inspect_state(self) -> CommandResult:
        snapshot = self.snapshot()
        status = (
            "No mesh loaded"
            if not snapshot.mesh_name
            else (
                f"{snapshot.mesh_name}: {snapshot.display_vertex_count:,} vertices, "
                f"{snapshot.display_triangle_count:,} triangles"
            )
        )
        self.events.publish(StatusEvent(status))
        return CommandResult.ok(
            status=status,
            changed=False,
            dirty=False,
            metadata={"analysis_snapshot": snapshot},
        )

    def snapshot(self) -> AnalysisSnapshot:
        mesh_object = self.state.mesh_object
        region = self.state.region_collection.active_region
        if mesh_object is None:
            return AnalysisSnapshot(
                curve_count=len(self.state.curve_collection.curves),
                surface_count=len(self.state.surface_collection.surfaces),
                brep_surface_count=len(self.state.brep_surface_collection.surfaces),
                active_region_id=None if region is None else region.id,
                active_region_triangle_count=(
                    0 if region is None else len(region.triangle_indices)
                ),
                selected_item=self.state.selected_item,
            )

        source_mesh = mesh_object.source_mesh
        display_mesh = mesh_object.display_mesh
        bounds = source_mesh.get_axis_aligned_bounding_box()
        matrix = build_object_transform_matrix(
            mesh_object.location,
            mesh_object.rotation,
            mesh_object.scale,
            mesh_object.origin,
        )
        minimum_values, maximum_values = transform_bounds(
            bounds.get_min_bound(),
            bounds.get_max_bound(),
            matrix,
        )
        minimum = tuple(float(value) for value in minimum_values)
        maximum = tuple(float(value) for value in maximum_values)
        return AnalysisSnapshot(
            mesh_name=str(mesh_object.name),
            source_vertex_count=len(source_mesh.vertices),
            source_triangle_count=len(source_mesh.triangles),
            display_vertex_count=len(display_mesh.vertices),
            display_triangle_count=len(display_mesh.triangles),
            display_proxy_enabled=bool(mesh_object.display_proxy_enabled),
            minimum_bound=minimum,  # type: ignore[arg-type]
            maximum_bound=maximum,  # type: ignore[arg-type]
            curve_count=len(self.state.curve_collection.curves),
            surface_count=len(self.state.surface_collection.surfaces),
            brep_surface_count=len(self.state.brep_surface_collection.surfaces),
            active_region_id=None if region is None else region.id,
            active_region_triangle_count=(
                0 if region is None else len(region.triangle_indices)
            ),
            selected_item=self.state.selected_item,
        )

    def compute_deviation(
        self,
        source_points: object,
        *,
        mesh: TriangleMeshData | None = None,
        mesh_revision: object | None = None,
        max_distance: float | None = None,
        signed: bool = False,
    ) -> CommandResult:
        target_mesh = mesh
        if target_mesh is None and self.state.mesh_object is not None:
            target_mesh = self.state.mesh_object.display_mesh
        if target_mesh is None or target_mesh.is_empty():
            return self._failure("Mesh deviation requires a loaded mesh.")
        if self.mesh_query_service is None:
            return self._failure("Mesh query service is unavailable.")
        try:
            index = self.mesh_query_service.get_index(
                target_mesh,
                mesh_revision=mesh_revision,
            )
            deviation = compute_point_deviation_to_mesh(
                source_points,
                index,  # type: ignore[arg-type]
                max_distance=max_distance,
                signed=signed,
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            return self._failure(str(exc))

        warning_values: tuple[str, ...] = ()
        if deviation.failed_sample_count:
            warning_values = (
                f"{deviation.failed_sample_count:,} deviation samples did not hit the mesh.",
            )
        status = self._deviation_status(deviation)
        self.events.publish(
            StatusEvent(
                status,
                level=(
                    StatusLevel.WARNING
                    if deviation.failed_sample_count
                    else StatusLevel.INFO
                ),
            )
        )
        mesh_name = (
            ""
            if self.state.mesh_object is None
            else str(self.state.mesh_object.name)
        )
        return CommandResult.ok(
            status=status,
            warnings=warning_values,
            changed=False,
            dirty=False,
            metadata={
                "deviation_result": deviation,
                "sample_count": len(deviation.samples),
                "failed_sample_count": deviation.failed_sample_count,
                "mean_distance": deviation.mean_distance,
                "max_distance": deviation.max_distance,
                "rms_distance": deviation.rms_distance,
                "source_mesh_name": mesh_name,
                "mesh_revision": mesh_revision,
                "query_backend": deviation.metadata.get("query_backend", ""),
            },
        )

    def _failure(self, message: str) -> CommandResult:
        normalized = str(message) or "Analysis failed."
        self.events.publish(StatusEvent(normalized, level=StatusLevel.ERROR))
        return CommandResult.failure(normalized, status=normalized)

    @staticmethod
    def _deviation_status(result: DeviationResult) -> str:
        count = len(result.samples)
        label = "sample" if count == 1 else "samples"
        return (
            f"Computed mesh deviation for {count:,} {label}: "
            f"mean {result.mean_distance:.6g}, max {result.max_distance:.6g}."
        )


__all__ = ("AnalysisController", "AnalysisSnapshot", "MeshIndexPort")
