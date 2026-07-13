"""Lightweight data contracts for future deviation analysis.

Computation and UI intentionally remain out of scope. These records provide a
stable target for later curve, surface, and BREP comparison workflows.
"""

from __future__ import annotations

from dataclasses import dataclass, field


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
