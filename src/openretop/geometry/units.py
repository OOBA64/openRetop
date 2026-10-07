"""Length units for imported meshes and exported CAD geometry."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_UNIT = "mm"


@dataclass(frozen=True)
class LengthUnit:
    code: str
    label: str
    millimetres: float

    def to_mm(self, value: float) -> float:
        return float(value) * self.millimetres

    def from_mm(self, value: float) -> float:
        return float(value) / self.millimetres


_UNITS = {
    "mm": LengthUnit("mm", "Millimetres", 1.0),
    "cm": LengthUnit("cm", "Centimetres", 10.0),
    "m": LengthUnit("m", "Metres", 1000.0),
    "in": LengthUnit("in", "Inches", 25.4),
}

UNIT_CODES = tuple(_UNITS)


def get_unit(code: object) -> LengthUnit:
    """Return the unit for ``code`` (case-insensitive); raises ValueError if unknown."""

    key = str(code).strip().lower()
    if key in ("inch", "inches", '"'):
        key = "in"
    try:
        return _UNITS[key]
    except KeyError:
        raise ValueError(
            f"Unsupported unit '{code}'. Expected one of: {', '.join(UNIT_CODES)}"
        ) from None


def unit_scale(from_code: str, to_code: str) -> float:
    """Multiplier converting a length in ``from_code`` into ``to_code``."""

    return get_unit(from_code).millimetres / get_unit(to_code).millimetres
