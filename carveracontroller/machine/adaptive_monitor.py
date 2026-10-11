"""Connection-scoped, shadow-only adaptive roughing monitor.

No transport or machine commands belong here. Thresholds are experimental:
baseline-relative droop is a load clue, never proof of stock contact.
"""

from __future__ import annotations

import math
from collections import deque
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from statistics import mean
from typing import Any

from .feed_recipe import FeedRecipe
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
    position: tuple[float, ...]
    context: dict[str, Any] = field(default_factory=dict)

    def valid(self) -> bool:
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

    def __init__(self) -> None:
        self.history: deque[Sample] = deque(maxlen=300)
        self.reset()

    def reset(self) -> None:
        self.enabled = True
        self.last: Sample | None = None
        self.baseline: dict[str, Any] | None = None
        self.capturing = False
        self.baseline_samples: list[Sample] = []
        self.proposed = 100.0
        self.filtered_droop = 0.0
        self.last_adjustment: float | None = None
        self.reason = "waiting for telemetry"
        self.fault: str | None = None
        self.history.clear()
        self.quality = TelemetryQuality()
        self.recipe: FeedRecipe | None = None
        self.outcomes: deque[dict[str, Any]] = deque(maxlen=100)
        self.proposals: deque[dict[str, Any]] = deque(maxlen=300)

    def configure_recipe(self, data: dict[str, Any]) -> dict[str, Any]:
        recipe = FeedRecipe(**data)
        self.recipe = recipe
        self.proposed = recipe.maximum_override
        self.last_adjustment = None
        return recipe.snapshot()

    @staticmethod
    def _conditions(sample: Sample) -> dict[str, Any]:
        context = dict(sample.context)
        context["tool_assembly_id"] = context.get("tool_assembly_id") or context.get("assembly_id")
        context["seating_revision"] = context.get("seating_revision") or context.get("seat_revision")
        source = context.get("source") or {}
        if "firmware_boot_id" not in context:
            context["firmware_boot_id"] = source.get("boot_id") if source.get("boot_id_valid") else None
        return {
            key: deepcopy(context.get(key))
            for key in (
                "tool_assembly_id",
                "tool",
                "seating_revision",
                "assembly_revision_id",
                "assignment_id",
                "accessory_commands",
                "firmware_boot_id",
            )
        }

    def record_outcome(self, outcome: dict[str, Any]) -> dict[str, Any]:
        """Associate operator observations with recorded proposals, without grading safety."""
        if not isinstance(outcome, dict) or not outcome.get("program_hash"):
            raise ValueError("outcome requires program_hash and operator measurements")
        allowed = (
            "program_hash",
            "operation",
            "timestamp",
            "dimensional_error_mm",
            "finish",
            "temperature_c",
            "tool_condition",
            "notes",
        )
        record = {key: outcome.get(key) for key in allowed}
        if isinstance(record["operation"], dict):
            record["operation"] = record["operation"].get("name") or record["operation"].get("label")
        if all(record.get(key) is None for key in allowed[3:]):
            raise ValueError("outcome needs at least one measured or observed result")
        for key in ("dimensional_error_mm", "temperature_c", "timestamp"):
            value = record.get(key)
            if value is not None and (not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError("outcome numeric values must be finite")
        record["proposals"] = [
            proposal
            for proposal in self.proposals
            if proposal["program_hash"] == record["program_hash"] and proposal["operation"] == record["operation"]
        ]
        record["evaluation"] = "operator observations; active control remains unavailable"
        self.outcomes.append(record)
        return record

    def capture_baseline(self) -> None:
        self.fault = None
        self.baseline = None
        self.baseline_samples = []
        self.capturing = True
        self.reason = "baseline armed: requires 5 s of stationary, unloaded spindle samples"

    def tick(self, now: float) -> None:
        if self.last is not None and now - self.last.timestamp > 0.8:
            self.fault = "telemetry stale: would hold; shadow sends no commands"
            self.reason = self.fault
            self.baseline_samples = []
            self.last_adjustment = None

    def observe(self, sample: Sample, *, packet_quality_recorded: bool = False) -> dict[str, Any]:
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
        if self.baseline:
            temperature = sample.context.get("spindle_temperature")
            reference_temperature = self.baseline.get("spindle_temperature")
            temperature_changed = (temperature is None) != (reference_temperature is None)
            if temperature is not None and reference_temperature is not None:
                temperature_changed = abs(temperature - reference_temperature) > 5
            if (
                abs(sample.commanded_rpm - self.baseline["commanded_rpm"]) > 1
                or self._conditions(sample) != self.baseline["conditions"]
                or temperature_changed
            ):
                self.baseline = None
                self.reason = "operating conditions changed; fresh baseline required"
        if self.capturing:
            stationary = sample.state == "Idle" and sample.feed == 0
            stable = sample.commanded_rpm > 0 and sample.rpm >= sample.commanded_rpm * 0.9
            if self.baseline_samples:
                first = self.baseline_samples[0]
                stable = stable and abs(sample.commanded_rpm - first.commanded_rpm) <= 1
                stable = stable and self._conditions(sample) == self._conditions(first)
                temperatures = (sample.context.get("spindle_temperature"), first.context.get("spindle_temperature"))
                if temperatures[0] is not None and temperatures[1] is not None:
                    stable = stable and abs(temperatures[0] - temperatures[1]) <= 5
                else:
                    stable = stable and temperatures[0] is temperatures[1]
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
                            "conditions": self._conditions(sample),
                            "spindle_temperature": sample.context.get("spindle_temperature"),
                            "temperature_tolerance_c": 5,
                            "unloaded_confirmation": "operator armed stationary spindle; stock contact not sensed",
                        }
                        self.capturing = False
                        self.proposed = min(self.recipe.maximum_override if self.recipe else 100.0, sample.override)
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
        operation = sample.context.get("operation")
        if isinstance(operation, dict):
            operation = operation.get("name") or operation.get("label")
        if self.recipe is None or not self.recipe.matches(
            sample.commanded_rpm,
            operation,
            sample.context.get("commanded_feed_mm_min"),
            sample.context.get("feed_resolution_mm_min", 0.102) / 2,
        ):
            self.reason = "matching cutter/material/operation chip-load recipe required; no feed proposal"
            return self.snapshot()
        floor, ceiling = self.recipe.minimum_override, self.recipe.maximum_override
        if sample.override < floor:
            self.reason = "observed feed below recipe chip-load floor: would hold; shadow sends no commands"
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
                self.proposed = max(floor, min(self.proposed, sample.override, ceiling) - 10)
                self.last_adjustment = sample.timestamp
            self.reason = (
                "load elevated; propose feed backoff" if self.proposed > floor else "at feed floor: would hold"
            )
        elif self.filtered_droop < 0.004 and not (sample.pwm is not None and sample.pwm > 0.75):
            if self.last_adjustment is None:
                self.last_adjustment = sample.timestamp
            elif sample.timestamp - self.last_adjustment >= 2:
                self.proposed = min(ceiling, self.proposed + 2)
                self.last_adjustment = sample.timestamp
            self.reason = "low observed load; slow feed recovery proposal"
        else:
            self.last_adjustment = sample.timestamp
            self.reason = "within experimental load band; retain proposal"
        program = sample.context.get("program") or {}
        self.proposals.append(
            {
                "timestamp": sample.timestamp,
                "program_hash": program.get("sha256"),
                "operation": operation,
                "proposed_override": self.proposed,
                "observed_override": sample.override,
                "reason": self.reason,
                "recipe": self.recipe.snapshot(),
            }
        )
        return self.snapshot()

    def snapshot(self, now: float | None = None) -> dict[str, Any]:
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
            "recipe": self.recipe.snapshot() if self.recipe else None,
            "outcome_count": len(self.outcomes),
        }
