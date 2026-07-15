"""VTK actor factory for finite section-plane frames."""

from __future__ import annotations

import numpy as np

from viewer.scene_types import SectionPlaneRenderItem
from viewer.vtk_actor_utils import polydata_actor, update_actor_polydata


def create_section_plane_actor(item: SectionPlaneRenderItem):
    points, lines = _plane_frame(item)
    return polydata_actor(points, lines, cell_kind="lines")


def update_section_plane_actor(actor: object, item: SectionPlaneRenderItem) -> None:
    points, lines = _plane_frame(item)
    update_actor_polydata(actor, points, lines, cell_kind="lines")


def _plane_frame(item: SectionPlaneRenderItem):
    origin = np.asarray(item.origin, dtype=float)
    normal = np.asarray(item.normal, dtype=float)
    reference = np.asarray([0.0, 0.0, 1.0], dtype=float)
    if abs(float(np.dot(normal, reference))) > 0.9:
        reference = np.asarray([0.0, 1.0, 0.0], dtype=float)
    u_axis = np.cross(normal, reference)
    u_axis /= max(float(np.linalg.norm(u_axis)), 1e-12)
    v_axis = np.cross(normal, u_axis)
    v_axis /= max(float(np.linalg.norm(v_axis)), 1e-12)
    extent = 1.0
    if item.frame_bounds is not None:
        extent = max(
            float(
                np.max(
                    np.asarray(item.frame_bounds[1], dtype=float)
                    - np.asarray(item.frame_bounds[0], dtype=float)
                )
            )
            * 0.5,
            1e-6,
        )
    points = np.asarray(
        [
            origin - u_axis * extent - v_axis * extent,
            origin + u_axis * extent - v_axis * extent,
            origin + u_axis * extent + v_axis * extent,
            origin - u_axis * extent + v_axis * extent,
        ]
    )
    lines = np.asarray([[0, 1], [1, 2], [2, 3], [3, 0]], dtype=int)
    return points, lines


__all__ = ("create_section_plane_actor", "update_section_plane_actor")
