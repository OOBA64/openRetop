"""Automatic segmentation of a scan into faces (RE-03)."""

from openretop.segmentation.segment import Segment, SegmentationResult, segment_mesh, triangle_adjacency

__all__ = ("Segment", "SegmentationResult", "segment_mesh", "triangle_adjacency")
