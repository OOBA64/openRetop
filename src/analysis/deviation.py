"""Point-to-mesh deviation contracts and accelerated computation."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from mesh.query_service import DEFAULT_MESH_QUERY_SERVICE
from mesh.spatial_index import MeshSpatialIndex
from mesh.triangle_mesh import TriangleMeshData


@dataclass(frozen=True)
class DeviationSample:
    source_point: tuple[float, float, float]
    nearest_point: tuple[float, float, float] | None
    distance: float
    source_index: int = 0
    signed_distance: float | None = None


@dataclass(frozen=True)
class DeviationResult:
    samples: tuple[DeviationSample, ...] = ()
    mean_distance: float = 0.0
    max_distance: float = 0.0
    rms_distance: float = 0.0
    failed_sample_count: int = 0
    metadata: dict[str, object] = field(default_factory=dict)


def compute_point_deviation_to_mesh(
    source_points: object,
    mesh_or_index: TriangleMeshData | MeshSpatialIndex,
    *,
    max_distance: float | None = None,
    signed: bool = False,
) -> DeviationResult:
    """Compute point deviations without adding viewport or heatmap behavior."""

    if isinstance(mesh_or_index, TriangleMeshData):
        query = DEFAULT_MESH_QUERY_SERVICE.query_closest_points(
            mesh_or_index,
            source_points,
            max_distance=max_distance,
            preserve_missed_points=True,
        )
    elif hasattr(mesh_or_index, "query_closest_points"):
        query = mesh_or_index.query_closest_points(
            source_points,
            max_distance=max_distance,
            preserve_missed_points=True,
        )
    else:
        raise TypeError(
            "mesh_or_index must be TriangleMeshData or a mesh spatial index."
        )

    samples: list[DeviationSample] = []
    successful_distances: list[float] = []
    for index in range(query.queried_point_count):
        hit = bool(query.hit_mask[index])
        distance = float(query.distances[index])
        if hit:
            successful_distances.append(abs(distance))
        samples.append(
            DeviationSample(
                source_point=tuple(float(value) for value in query.source_points[index]),
                nearest_point=(
                    tuple(float(value) for value in query.closest_points[index])
                    if hit
                    else None
                ),
                distance=distance,
                source_index=index,
                signed_distance=None,
            )
        )

    distances = np.asarray(successful_distances, dtype=float)
    return DeviationResult(
        samples=tuple(samples),
        mean_distance=float(np.mean(distances)) if len(distances) else 0.0,
        max_distance=float(np.max(distances)) if len(distances) else 0.0,
        rms_distance=(
            float(np.sqrt(np.mean(np.square(distances)))) if len(distances) else 0.0
        ),
        failed_sample_count=int(query.missed_count),
        metadata={
            "query_backend": query.backend,
            "index_build_time_seconds": query.build_time_seconds,
            "query_time_seconds": query.query_time_seconds,
            "queried_point_count": query.queried_point_count,
            "hit_count": query.hit_count,
            "failed_sample_count": query.missed_count,
            "signed_requested": bool(signed),
            "signed_distance_available": False,
            **query.metadata,
        },
    )
