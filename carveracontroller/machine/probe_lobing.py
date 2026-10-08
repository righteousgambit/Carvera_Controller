"""Characterise a touch probe's direction-dependent error.

A touch-trigger probe does not fire the instant the stylus contacts a
surface: the stylus deflects first, and how far it deflects depends on which
way it is pushed. On a three-lobe kinematic seat that variation is periodic
around the probe's axis, and it is the dominant error in this class of probe
-- larger than the machine's own repeatability.

It is also systematic. Measure it once and it can be subtracted, or at least
designed around by always approaching a feature the same way.

The tip diameter derivation matches the firmware's own M460: for a bore the
effective diameter is `known - measured`, for a boss `measured - known`
(ZProbe.cpp:2364 and :2423). Measuring at several angles instead of averaging
them away is the only difference.

Kivy-free by contract.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import Enum

# Lobing below this is smaller than the machine's own repeatability, so
# compensating for it would be measuring noise.
NEGLIGIBLE_LOBING_MM = 0.005
# Above this the probe dominates every measurement taken with it.
SEVERE_LOBING_MM = 0.030


class FeatureType(Enum):
    BORE = "bore"
    BOSS = "boss"


class LobingQuality(Enum):
    NEGLIGIBLE = "negligible"
    MODERATE = "moderate"
    SEVERE = "severe"


@dataclass(frozen=True)
class LobingSample:
    angle_degrees: float
    measured_diameter: float


@dataclass(frozen=True)
class LobingMap:
    known_diameter: float
    feature: FeatureType
    samples: tuple[LobingSample, ...]
    tip_diameters: tuple[float, ...]
    """Effective tip diameter implied by each sample, in sample order."""

    @property
    def effective_tip_diameter(self) -> float:
        """The single value to persist with config-set.

        The mean across directions, which is the best compromise when the
        probe is used in all of them.
        """
        return sum(self.tip_diameters) / len(self.tip_diameters)

    @property
    def lobing_amplitude(self) -> float:
        """Peak-to-peak spread of the implied tip diameter across directions."""
        return max(self.tip_diameters) - min(self.tip_diameters)

    @property
    def quality(self) -> LobingQuality:
        if self.lobing_amplitude >= SEVERE_LOBING_MM:
            return LobingQuality.SEVERE
        if self.lobing_amplitude >= NEGLIGIBLE_LOBING_MM:
            return LobingQuality.MODERATE
        return LobingQuality.NEGLIGIBLE

    @property
    def worst_angle(self) -> float:
        """Approach angle whose implied tip diameter deviates most from the mean."""
        mean = self.effective_tip_diameter
        worst = max(zip(self.samples, self.tip_diameters), key=lambda p: abs(p[1] - mean))
        return worst[0].angle_degrees

    @property
    def best_angle(self) -> float:
        """Approach angle closest to the mean, i.e. least corrected by averaging."""
        mean = self.effective_tip_diameter
        best = min(zip(self.samples, self.tip_diameters), key=lambda p: abs(p[1] - mean))
        return best[0].angle_degrees

    def correction_at(self, angle_degrees: float) -> float:
        """Tip diameter correction for one approach direction.

        Add this to the configured effective diameter to get the value that
        would have been right for a feature probed at this angle. Interpolated
        between samples, wrapping at 360 degrees.
        """
        if len(self.samples) == 1:
            return 0.0

        mean = self.effective_tip_diameter
        target = angle_degrees % 360.0
        points = sorted(
            ((s.angle_degrees % 360.0, tip - mean) for s, tip in zip(self.samples, self.tip_diameters)),
            key=lambda p: p[0],
        )

        for index, (angle, deviation) in enumerate(points):
            if math.isclose(angle, target):
                return deviation
            if angle > target:
                previous_angle, previous_deviation = points[index - 1]
                if index == 0:
                    previous_angle, previous_deviation = points[-1][0] - 360.0, points[-1][1]
                span = angle - previous_angle
                if span <= 0:
                    return deviation
                ratio = (target - previous_angle) / span
                return previous_deviation + (deviation - previous_deviation) * ratio

        # Past the last sample: wrap around to the first.
        last_angle, last_deviation = points[-1]
        first_angle, first_deviation = points[0]
        span = (first_angle + 360.0) - last_angle
        if span <= 0:
            return last_deviation
        ratio = (target - last_angle) / span
        return last_deviation + (first_deviation - last_deviation) * ratio


def build_lobing_map(
    known_diameter: float,
    samples: Sequence[LobingSample],
    feature: FeatureType = FeatureType.BORE,
) -> LobingMap:
    """Derive a lobing map from measurements of a feature of known size."""
    if known_diameter <= 0:
        raise ValueError("known_diameter must be positive")
    if not samples:
        raise ValueError("at least one sample is required")

    if feature is FeatureType.BORE:
        tips = tuple(known_diameter - s.measured_diameter for s in samples)
    else:
        tips = tuple(s.measured_diameter - known_diameter for s in samples)

    return LobingMap(
        known_diameter=known_diameter,
        feature=feature,
        samples=tuple(samples),
        tip_diameters=tips,
    )


def summarise(lobing_map: LobingMap) -> str:
    """Human-readable summary, including what to do with the numbers."""
    amplitude_um = lobing_map.lobing_amplitude * 1000
    lines = [
        f"Effective tip diameter: {lobing_map.effective_tip_diameter:.4f} mm",
        f"Lobing (peak to peak):  {amplitude_um:.1f} um across {len(lobing_map.samples)} directions",
        f"Worst approach angle:   {lobing_map.worst_angle:.0f} deg",
    ]
    if lobing_map.quality is LobingQuality.NEGLIGIBLE:
        lines.append("Lobing is below the machine's own repeatability; no compensation needed.")
    elif lobing_map.quality is LobingQuality.MODERATE:
        lines.append(
            "Lobing is significant. Approach features from a consistent direction so the error "
            "cancels when comparing measurements."
        )
    else:
        lines.append(
            "Lobing dominates every measurement from this probe. Check the tip is concentric to "
            "the shank before trusting any probed dimension."
        )
    lines.append(
        f"Persist the diameter with: config-set sd zprobe.probe_tip_diameter {lobing_map.effective_tip_diameter:.4f}"
    )
    return "\n".join(lines)
