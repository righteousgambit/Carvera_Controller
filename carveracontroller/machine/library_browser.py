"""Pure, unit-aware browsing of saved profiles; no asset IO or machine writes."""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from carveracontroller.machine.quantities import QuantityError, parse_quantity


@dataclass(frozen=True)
class CutterFilter:
    shape: str = ""
    vendor: str = ""
    minimum: float | None = None
    maximum: float | None = None
    shank: float | None = None
    assets: str = "All assets"

    @classmethod
    def from_text(cls, *, shape="", vendor="", minimum="", maximum="", shank="", assets="All assets"):
        def dimension(value):
            return parse_quantity(value, minimum=0.000001, maximum=1000) if value.strip() else None

        low, high, shaft = dimension(minimum), dimension(maximum), dimension(shank)
        if low is not None and high is not None and low > high:
            raise QuantityError("Minimum cutting diameter exceeds maximum")
        if assets not in ("All assets", "CAD reference", "Drawing reference", "Dimensions only"):
            raise QuantityError("Unknown asset filter")
        return cls(shape, vendor.strip(), low, high, shaft, assets)

    @property
    def active(self):
        return bool(
            self.shape or self.vendor or self.minimum or self.maximum or self.shank or self.assets != "All assets"
        )

    def matches(self, record):
        if self.shape and record.get("shape") != self.shape:
            return False
        if self.vendor.casefold() not in record.get("vendor", "").casefold():
            return False
        diameter = record.get("diameter")
        if self.minimum is not None and (diameter is None or diameter < self.minimum - 1e-6):
            return False
        if self.maximum is not None and (diameter is None or diameter > self.maximum + 1e-6):
            return False
        if self.shank is not None and (
            record.get("shank_diameter") is None
            or not isclose(record["shank_diameter"], self.shank, rel_tol=0, abs_tol=1e-6)
        ):
            return False
        cad, drawing = bool(record.get("geometry_path")), bool(record.get("drawing_path"))
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


def browse_profiles(records, query="", *, cutter_filter=None, sort="Name"):
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
    if sort == "Diameter":
        key = lambda item: (
            item.get("diameter") is None,
            item.get("diameter") or 0,
            item["name"].casefold(),
            item["id"],
        )
    elif sort == "Vendor":
        key = lambda item: (item.get("vendor", "").casefold(), item["name"].casefold(), item["id"])
    else:
        key = lambda item: (item["name"].casefold(), item["id"])
    return sorted(result, key=key)
