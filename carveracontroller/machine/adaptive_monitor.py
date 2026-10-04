"""Connection-scoped, shadow-only adaptive roughing monitor.

No transport or machine commands belong here. Thresholds are experimental:
baseline-relative droop is a load clue, never proof of stock contact.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import asdict, dataclass
from statistics import mean

from .telemetry_quality import TelemetryQuality

FILTER_TIME_CONSTANT = 0.4


@dataclass(frozen=True)
class Sample:
    timestamp: float
    state: str
    rpm: float
    commanded_rpm: float
    pwm: float | None
    feed: float
    override: float
    position: tuple

    def valid(self):
        values = (self.timestamp, self.rpm, self.commanded_rpm, self.feed, self.override, *self.position)
        return (
            all(math.isfinite(v) for v in values)
            and self.rpm >= 0
            and self.commanded_rpm >= 0
            and self.feed >= 0
            and 0 < self.override <= 200
            and (self.pwm is None or (math.isfinite(self.pwm) and 0 <= self.pwm <= 1))
        )


class AdaptiveMonitor:
    """Compute bounded proposals only; active feed control is intentionally absent."""

    def __init__(self):
        self.history = deque(maxlen=300)
        self.reset()

    def reset(self):
        self.enabled = True
        self.last = None
        self.baseline = None
        self.capturing = False
        self.baseline_samples = []
        self.proposed = 100.0
        self.filtered_droop = 0.0
        self.last_adjustment = None
        self.reason = "waiting for telemetry"
        self.fault = None
        self.history.clear()
        self.quality = TelemetryQuality()

    def capture_baseline(self):
        self.fault = None
        self.baseline = None
        self.baseline_samples = []
        self.capturing = True
        self.reason = "baseline armed: requires 5 s of stationary, unloaded spindle samples"

    def tick(self, now):
        if self.last is not None and now - self.last.timestamp > 0.8:
            self.fault = "telemetry stale: would hold; shadow sends no commands"
            self.reason = self.fault
            self.baseline_samples = []
            self.last_adjustment = None

    def observe(self, sample, *, packet_quality_recorded=False):
        if not packet_quality_recorded:
            self.quality.record(
                sample.timestamp, valid=sample.valid(), rpm=sample.rpm, pwm_available=sample.pwm is not None
            )
        if not sample.valid():
            self.fault = "invalid telemetry: would hold; shadow sends no commands"
            self.reason = self.fault
            self.baseline = None
            self.baseline_samples = []
            return self.snapshot()
        previous = self.last
        self.last = sample
        self.history.append(sample)
        if self.fault:
            self.reason = self.fault
            return self.snapshot()
        if previous and (sample.timestamp <= previous.timestamp or sample.timestamp - previous.timestamp > 0.8):
            self.baseline_samples = []
            self.last_adjustment = None
            self.filtered_droop = 0.0
            self.fault = "telemetry discontinuity: reset or capture a fresh baseline"
            self.reason = self.fault
            return self.snapshot()
        if not self.enabled:
            self.reason = "monitor off"
            return self.snapshot()
        if self.baseline and (abs(sample.commanded_rpm - self.baseline["commanded_rpm"]) > 1):
            self.baseline = None
        if self.capturing:
            stationary = sample.state == "Idle" and sample.feed == 0
            stable = sample.commanded_rpm > 0 and sample.rpm >= sample.commanded_rpm * 0.9
            if self.baseline_samples:
                first = self.baseline_samples[0]
                stable = stable and abs(sample.commanded_rpm - first.commanded_rpm) <= 1
                stationary = stationary and all(abs(a - b) < 0.01 for a, b in zip(sample.position, first.position))
            if not stationary or not stable:
                self.baseline_samples = []
                self.reason = "baseline waiting for stationary spindle at speed"
            else:
                self.baseline_samples.append(sample)
                if sample.timestamp - self.baseline_samples[0].timestamp >= 5:
                    rpms = [s.rpm for s in self.baseline_samples]
                    if max(rpms) - min(rpms) > sample.commanded_rpm * 0.005:
                        self.baseline_samples = []
                        self.reason = "baseline too noisy; collecting again"
                    else:
                        pwms = [s.pwm for s in self.baseline_samples if s.pwm is not None]
                        self.baseline = {
                            "rpm": mean(rpms),
                            "commanded_rpm": sample.commanded_rpm,
                            "pwm": mean(pwms) if len(pwms) == len(rpms) else None,
                            "rpm_range": max(rpms) - min(rpms),
                            "samples": len(rpms),
                        }
                        self.capturing = False
                        self.proposed = min(100.0, sample.override)
                        self.reason = "baseline captured; waiting for cutting feed"
                else:
                    self.reason = "collecting unloaded baseline"
            return self.snapshot()
        if not self.baseline:
            self.reason = "baseline required (adaptive baseline); no feed proposal"
            return self.snapshot()
        if sample.state != "Run" or sample.feed <= 0:
            self.last_adjustment = None
            self.filtered_droop = 0.0
            self.reason = "outside cutting feed; no feed proposal"
            return self.snapshot()
        droop = max(0.0, (self.baseline["rpm"] - sample.rpm) / self.baseline["rpm"])
        dt = sample.timestamp - previous.timestamp if previous else 0.2
        alpha = 1 - math.exp(-dt / FILTER_TIME_CONSTANT)
        self.filtered_droop += alpha * (droop - self.filtered_droop)
        pwm_high = sample.pwm is not None and sample.pwm >= 0.95
        if droop >= 0.05:
            self.fault = "severe RPM droop: would hold; shadow sends no commands"
            self.reason = self.fault
            self.last_adjustment = sample.timestamp
        elif self.filtered_droop >= 0.012 or pwm_high:
            if self.last_adjustment is None or sample.timestamp - self.last_adjustment >= 0.4:
                self.proposed = max(40.0, min(self.proposed, sample.override) - 10)
                self.last_adjustment = sample.timestamp
            self.reason = "load elevated; propose feed backoff" if self.proposed > 40 else "at feed floor: would hold"
        elif self.filtered_droop < 0.004 and not (sample.pwm is not None and sample.pwm > 0.75):
            if self.last_adjustment is None:
                self.last_adjustment = sample.timestamp
            elif sample.timestamp - self.last_adjustment >= 2:
                self.proposed = min(100.0, self.proposed + 2)
                self.last_adjustment = sample.timestamp
            self.reason = "low observed load; slow feed recovery proposal"
        else:
            self.last_adjustment = sample.timestamp
            self.reason = "within experimental load band; retain proposal"
        return self.snapshot()

    def snapshot(self, now=None):
        return {
            "mode": "shadow" if self.enabled else "off",
            "reason": self.reason,
            "baseline": self.baseline,
            "filtered_droop": self.filtered_droop,
            "proposed_override": self.proposed,
            "sample": asdict(self.last) if self.last else None,
            "active_control_available": False,
            "telemetry_quality": self.quality.snapshot(now),
            "filter_time_constant_s": FILTER_TIME_CONSTANT,
        }
