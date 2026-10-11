"""Operator-supplied chip-load bounds for shadow feed proposals, in mm/min.

No material recommendations or physical qualification are inferred here.
"""

import math
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FeedRecipe:
    cutter: str
    material: str
    operation: str
    rpm: float
    flutes: int
    programmed_feed_mm_min: float
    chipload_min_mm: float
    chipload_max_mm: float

    def __post_init__(self):
        if not all(isinstance(s, str) and s.strip() for s in (self.cutter, self.material, self.operation)):
            raise ValueError("recipe requires cutter, material and operation identity")
        values = (self.rpm, self.programmed_feed_mm_min, self.chipload_min_mm, self.chipload_max_mm)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) and v > 0 for v in values):
            raise ValueError("recipe RPM, feed and chip loads must be finite and positive")
        if isinstance(self.flutes, bool) or not isinstance(self.flutes, int) or not 1 <= self.flutes <= 64:
            raise ValueError("flutes must be an integer from 1 to 64")
        if self.chipload_min_mm > self.chipload_max_mm:
            raise ValueError("minimum chip load exceeds maximum")
        if not (
            math.isfinite(self.minimum_override)
            and self.minimum_override > 0
            and math.isfinite(self.maximum_override)
            and self.maximum_override > 0
        ):
            raise ValueError("derived chip-load override bounds must be finite and positive")
        if self.minimum_override > self.maximum_override:
            raise ValueError("programmed feed is below the minimum chip load")

    @property
    def minimum_override(self):
        return self.chipload_min_mm * self.rpm * self.flutes / self.programmed_feed_mm_min * 100

    @property
    def maximum_override(self):
        return min(100.0, self.chipload_max_mm * self.rpm * self.flutes / self.programmed_feed_mm_min * 100)

    def matches(self, rpm, operation=None, commanded_feed_mm_min=None, feed_tolerance_mm_min=0.051):
        if operation != self.operation or commanded_feed_mm_min is None:
            return False
        return (
            abs(rpm - self.rpm) <= 1
            and abs(commanded_feed_mm_min - self.programmed_feed_mm_min) <= feed_tolerance_mm_min
        )

    def snapshot(self):
        return dict(
            asdict(self),
            minimum_override=self.minimum_override,
            maximum_override=self.maximum_override,
            qualification="operator supplied; physical cutting outcome unverified",
        )
