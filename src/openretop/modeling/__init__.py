"""The model built from the scan with the surfacing tools (milestone S)."""

from openretop.modeling.document import KIND_LABELS, PALETTE, ModelDocument, ModelEntity, entity_from_result
from openretop.modeling.scan_selection import DEFAULT_SMART_ANGLE, ScanSelection, SourceMapping, selected_patch

__all__ = (
    "DEFAULT_SMART_ANGLE",
    "KIND_LABELS",
    "PALETTE",
    "ModelDocument",
    "ModelEntity",
    "ScanSelection",
    "SourceMapping",
    "entity_from_result",
    "selected_patch",
)
