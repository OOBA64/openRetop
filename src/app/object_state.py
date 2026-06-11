"""Mesh object state for the loaded editable object."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mesh.display_proxy import DEFAULT_PROXY_QUALITY
from mesh.triangle_mesh import TriangleMeshData


@dataclass
class MeshObjectState:
    """Selection-oriented state for the loaded mesh object."""

    source_mesh: TriangleMeshData
    display_mesh: TriangleMeshData
    file_path: Path | None
    name: str
    origin: np.ndarray
    location: np.ndarray
    rotation: np.ndarray
    scale: float = 1.0
    transform_matrix: np.ndarray | None = None
    source_triangle_count: int = 0
    display_triangle_count: int = 0
    display_proxy_enabled: bool = False
    display_reduction_percent: float = 0.0
    proxy_quality: str = DEFAULT_PROXY_QUALITY
    source_bounds_min: np.ndarray | None = None
    source_bounds_max: np.ndarray | None = None
