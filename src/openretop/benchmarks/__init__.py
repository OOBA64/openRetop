"""Round-trip benchmarks: known CAD parts turned into scan-like meshes (RE-01).

Every reverse-engineering tool is measured against these: the reference part's exact
parameters (radii, axes, volume, which triangle came from which face) are known, so a fit,
a segmentation or a rebuilt solid can be scored with numbers instead of by eye.
Needs CadQuery (OpenCASCADE), which the CAD workflows need anyway.
"""

from openretop.benchmarks.parts import (
    BENCHMARKS,
    ReferencePart,
    ScanMesh,
    distance_to_reference,
    make_part,
    scan_from_part,
)

__all__ = (
    "BENCHMARKS",
    "ReferencePart",
    "ScanMesh",
    "distance_to_reference",
    "make_part",
    "scan_from_part",
)
