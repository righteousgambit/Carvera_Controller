"""Pure, unit-aware browsing of saved profiles; no asset IO or machine writes."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from math import isclose, isfinite
from typing import TypeVar

from carveracontroller.machine.quantities import QuantityError, parse_quantity

Record = TypeVar("Record", bound=Mapping[str, object])


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _dimension(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None
    return number if isfinite(number) and number > 0 else None


@dataclass(frozen=True)
class CutterFilter:
    shape: str = ""
    vendor: str = ""
    minimum: float | None = None
    maximum: float | None = None
    shank: float | None = None
    assets: str = "All assets"

    def __post_init__(self) -> None:
        if self.assets not in ("All assets", "CAD reference", "Drawing reference", "Dimensions only"):
            raise QuantityError("Unknown asset filter")
        for value in (self.minimum, self.maximum, self.shank):
            if value is not None and (_dimension(value) is None or not 0.000001 <= value <= 1000):
                raise QuantityError("Filter dimensions must be finite positive millimetres up to 1000")
        if self.minimum is not None and self.maximum is not None and self.minimum > self.maximum:
            raise QuantityError("Minimum cutting diameter exceeds maximum")

    @classmethod
    def from_text(
        cls,
        *,
        shape: str = "",
        vendor: str = "",
        minimum: str = "",
        maximum: str = "",
        shank: str = "",
        assets: str = "All assets",
    ) -> CutterFilter:
        def dimension(value: str) -> float | None:
            return parse_quantity(value, minimum=0.000001, maximum=1000) if value.strip() else None

        low, high, shaft = dimension(minimum), dimension(maximum), dimension(shank)
        if low is not None and high is not None and low > high:
            raise QuantityError("Minimum cutting diameter exceeds maximum")
        if assets not in ("All assets", "CAD reference", "Drawing reference", "Dimensions only"):
            raise QuantityError("Unknown asset filter")
        return cls(shape, vendor.strip(), low, high, shaft, assets)

    @property
    def active(self) -> bool:
        return bool(
            self.shape or self.vendor or self.minimum or self.maximum or self.shank or self.assets != "All assets"
        )

    @property
    def summary(self) -> str:
        parts = []
        if self.shape:
            parts.append(self.shape.replace("_", " "))
        if self.vendor:
            parts.append(f"Vendor: {self.vendor}")
        if self.minimum is not None and self.maximum is not None:
            parts.append(f"Diameter {self.minimum:g}–{self.maximum:g} mm")
        elif self.minimum is not None:
            parts.append(f"Diameter at least {self.minimum:g} mm")
        elif self.maximum is not None:
            parts.append(f"Diameter at most {self.maximum:g} mm")
        if self.shank is not None:
            parts.append(f"Shank {self.shank:g} mm")
        if self.assets != "All assets":
            parts.append(self.assets)
        return " · ".join(parts)

    def matches(self, record: Mapping[str, object]) -> bool:
        if self.shape and record.get("shape") != self.shape:
            return False
        if self.vendor.casefold() not in _text(record.get("vendor")).casefold():
            return False
        diameter = _dimension(record.get("diameter"))
        if self.minimum is not None and (diameter is None or diameter < self.minimum - 1e-6):
            return False
        if self.maximum is not None and (diameter is None or diameter > self.maximum + 1e-6):
            return False
        shank = _dimension(record.get("shank_diameter"))
        if self.shank is not None and (shank is None or not isclose(shank, self.shank, rel_tol=0, abs_tol=1e-6)):
            return False
        cad, drawing = bool(_text(record.get("geometry_path"))), bool(_text(record.get("drawing_path")))
        return (
            self.assets == "All assets"
            or self.assets == "CAD reference"
            and cad
            or self.assets == "Drawing reference"
            and drawing
            or self.assets == "Dimensions only"
            and not cad
            and not drawing
        )


def browse_profiles(
    records: Iterable[Record], query: str = "", *, cutter_filter: CutterFilter | None = None, sort: str = "Name"
) -> list[Record]:
    """Return references to matching saved records without changing their order/data."""
    tokens = query.casefold().split()
    result = []
    for record in records:
        haystack = " ".join(
            str(record.get(key, "")) for key in ("name", "vendor", "product_id", "notes", "shape", "host", "model")
        ).casefold()
        if not all(token in haystack for token in tokens):
            continue
        if cutter_filter and not cutter_filter.matches(record):
            continue
        result.append(record)

    def key(item: Record) -> tuple[bool, float, str, str, str]:
        name, identifier = _text(item.get("name")).casefold(), _text(item.get("id"))
        if sort == "Diameter":
            diameter = _dimension(item.get("diameter"))
            return diameter is None, diameter or 0, "", name, identifier
        if sort == "Vendor":
            return False, 0, _text(item.get("vendor")).casefold(), name, identifier
        return False, 0, "", name, identifier

    return sorted(result, key=key)
