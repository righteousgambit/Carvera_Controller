"""Versioned capability evidence and command planning, independent of UI/transport.

A profile declaration is not proof of installed hardware. Plans require fresh
observations, and an ``ok`` acknowledges acceptance, not physical completion.
Firmware bounds: community v2.1.0c release (feab653); dev f1db00f removes PWM.
https://github.com/Carvera-Community/Carvera_Community_Firmware/releases/tag/v2.1.0c
https://github.com/Carvera-Community/Carvera_Community_Firmware/releases/tag/dev
"""

from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Protocol, cast

SCHEMA_VERSION = 1


def _record(value: object, name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{name} must be an object with text keys")
    return value


def _text(value: object, name: str, *, required: bool = False) -> str:
    if not isinstance(value, str) or (required and not value.strip()):
        raise ValueError(f"{name} must be text")
    return value


def _number(value: object, name: str) -> int | float | None:
    if value is None:
        return None
    if type(value) not in (int, float):
        raise ValueError(f"{name} must be a finite number or null")
    numeric = cast("int | float", value)
    try:
        finite = math.isfinite(numeric)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be a finite number or null")
    return numeric


def _sequence(value: object, name: str) -> list[Any] | tuple[Any, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{name} must be an array")
    return value


class Support(str, Enum):
    UNKNOWN = "unknown"
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class CapabilityEvidence:
    declared: Support = Support.UNKNOWN
    actual: Support = Support.UNKNOWN
    observed_at: float | None = None
    source: str = ""

    def permits(self, now: float, max_age: float = 30.0) -> bool:
        return (
            self.actual == Support.SUPPORTED
            and self.declared != Support.UNSUPPORTED
            and self.observed_at is not None
            and 0 <= now - self.observed_at <= max_age
        )

    @property
    def conflict(self) -> bool:
        return self.declared != Support.UNKNOWN and self.actual != Support.UNKNOWN and self.declared != self.actual


@dataclass(frozen=True)
class AxisDefinition:
    name: str
    kind: str = "linear"
    minimum: float | None = None
    maximum: float | None = None

    def __post_init__(self) -> None:
        if self.name not in "XYZABC" or len(self.name) != 1 or self.kind not in ("linear", "rotary"):
            raise ValueError("invalid axis definition")
        for value in (self.minimum, self.maximum):
            if value is not None and not math.isfinite(value):
                raise ValueError("axis limits must be finite")
        if self.minimum is not None and self.maximum is not None and self.minimum >= self.maximum:
            raise ValueError("axis limits must be ordered")

    def contains(self, value: float) -> bool:
        return (
            math.isfinite(value)
            and self.minimum is not None
            and self.maximum is not None
            and self.minimum <= value <= self.maximum
        )


@dataclass(frozen=True)
class FirmwareIdentity:
    family: str = "unknown"
    version: str = ""
    revision: str = ""


@dataclass
class CapabilitySet:
    machine_id: str
    backend: str = "carvera"
    revision: int = 1
    firmware: FirmwareIdentity = field(default_factory=FirmwareIdentity)
    axes: tuple[AxisDefinition, ...] = ()
    topology: str = "cartesian"
    features: dict[str, CapabilityEvidence] = field(default_factory=dict)
    telemetry_fields: tuple[str, ...] = ()
    tool_slots: tuple[int, ...] = ()
    execution_available: bool = True

    def __post_init__(self) -> None:
        if self.revision < 1 or self.topology not in ("cartesian", "table", "table-table", "head-table", "head-head"):
            raise ValueError("invalid capability revision or topology")
        if len({axis.name for axis in self.axes}) != len(self.axes):
            raise ValueError("duplicate axis")
        if len(set(self.tool_slots)) != len(self.tool_slots) or any(t < 1 or t > 255 for t in self.tool_slots):
            raise ValueError("invalid tool slots")

    def require(self, feature: str, now: float, max_age: float = 30.0) -> None:
        if not self.execution_available:
            raise ValueError(f"{self.backend} execution adapter unavailable")
        if not self.features.get(feature, CapabilityEvidence()).permits(now, max_age):
            raise ValueError(f"{feature} is unknown, stale, unsupported, or conflicts with profile")

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": SCHEMA_VERSION, **asdict(self)}

    @classmethod
    def from_dict(cls, data: object) -> CapabilitySet:
        record = _record(data, "capability set")
        if type(record.get("schema_version")) is not int or record.get("schema_version") != SCHEMA_VERSION:
            raise ValueError("unsupported capability schema")
        revision = record.get("revision")
        if type(revision) is not int or revision < 1:
            raise ValueError("capability revision must be a positive integer")
        execution = record.get("execution_available")
        if type(execution) is not bool:
            raise ValueError("execution availability must be a boolean")
        firmware = _record(record.get("firmware"), "firmware identity")
        axes = []
        for item in _sequence(record.get("axes"), "axes"):
            axis = _record(item, "axis")
            axes.append(
                AxisDefinition(
                    _text(axis.get("name"), "axis name", required=True),
                    _text(axis.get("kind", "linear"), "axis kind", required=True),
                    _number(axis.get("minimum"), "axis minimum"),
                    _number(axis.get("maximum"), "axis maximum"),
                )
            )
        features = {}
        for name, item in _record(record.get("features"), "features").items():
            evidence = _record(item, "capability evidence")
            features[_text(name, "feature name", required=True)] = CapabilityEvidence(
                declared=Support(_text(evidence.get("declared"), "declared support")),
                actual=Support(_text(evidence.get("actual"), "observed support")),
                observed_at=_number(evidence.get("observed_at"), "observation time"),
                source=_text(evidence.get("source"), "evidence source"),
            )
        slots = _sequence(record.get("tool_slots"), "tool slots")
        if any(type(slot) is not int for slot in slots):
            raise ValueError("tool slots must be integers")
        return cls(
            machine_id=_text(record.get("machine_id"), "machine ID", required=True),
            backend=_text(record.get("backend"), "backend", required=True),
            revision=revision,
            firmware=FirmwareIdentity(
                _text(firmware.get("family", "unknown"), "firmware family"),
                _text(firmware.get("version", ""), "firmware version"),
                _text(firmware.get("revision", ""), "firmware revision"),
            ),
            axes=tuple(axes),
            topology=_text(record.get("topology"), "topology", required=True),
            features=features,
            telemetry_fields=tuple(
                _text(value, "telemetry field", required=True)
                for value in _sequence(record.get("telemetry_fields"), "telemetry fields")
            ),
            tool_slots=tuple(slots),
            execution_available=execution,
        )


def carvera_capabilities(
    machine_id: str,
    model: str,
    firmware: FirmwareIdentity,
    now: float,
    axes: tuple[AxisDefinition, ...] = (),
    has_atc: bool | None = None,
    rotary: bool = False,
) -> CapabilitySet:
    """Build from an actual identity readback. Never call with a saved profile identity.

    Only exact published release versions are recognized: future/dev firmware
    requires fresh feature discovery. ATC is an independent hardware observation.
    """
    if model not in ("C1", "CA1", "Air"):
        raise ValueError("unknown Carvera model")
    stable = firmware.family == "community" and firmware.version in ("2.1.0", "2.1.0c")
    dev = firmware.family == "community" and firmware.revision.startswith("f1db00f")
    known = stable or dev

    def evidence(enabled: bool) -> CapabilityEvidence:
        return CapabilityEvidence(
            actual=Support.SUPPORTED if enabled else Support.UNKNOWN,
            observed_at=now,
            source=f"identity:{firmware.family}:{firmware.version}:{firmware.revision}",
        )

    features = {
        name: evidence(known) for name in ("status", "spindle", "manual_tools", "probe", "feed_override", "named_io")
    }
    features.update(
        {name: evidence(stable) for name in ("custom_slots", "instant_override", "inverse_time", "lookahead")}
    )
    features["atc"] = CapabilityEvidence(
        actual=Support.UNKNOWN if has_atc is None else (Support.SUPPORTED if has_atc else Support.UNSUPPORTED),
        observed_at=now,
        source="hardware readback",
    )
    features["rotary"] = evidence(rotary and known)
    for name in ("rigid_tapping", "tcp", "coolant", "mill_turn"):
        features[name] = CapabilityEvidence(
            actual=Support.UNSUPPORTED if known else Support.UNKNOWN,
            observed_at=now,
            source="not implemented by Carvera adapter",
        )
    fields: tuple[str, ...] = ("position", "rpm", "feed", "overrides") if known else ()
    if stable:
        fields += ("pwm", "executed_line", "queued_line")
    return CapabilitySet(machine_id, firmware=firmware, axes=axes, features=features, telemetry_fields=fields)


@dataclass(frozen=True)
class CommandPlan:
    commands: tuple[str, ...]
    capability: str
    effect: str = "read"
    acknowledgment: str = "acceptance"


class BackendAdapter(Protocol):
    capabilities: CapabilitySet

    def snapshot(self, now: float) -> CommandPlan: ...
    def feed_override(self, percent: float, now: float, instant: bool = False) -> CommandPlan: ...


class CarveraAdapter:
    def __init__(self, capabilities: CapabilitySet) -> None:
        if capabilities.backend != "carvera":
            raise ValueError("wrong backend")
        self.capabilities = capabilities

    def snapshot(self, now: float) -> CommandPlan:
        self.capabilities.require("status", now)
        return CommandPlan(("?",), "status", acknowledgment="status response")

    def query_slots(self, now: float) -> CommandPlan:
        self.capabilities.require("custom_slots", now)
        return CommandPlan(("M889",), "custom_slots", acknowledgment="slot readback")

    def write_slot(
        self, slot: int, position: tuple[float, float, float] | None, now: float, *, opt_in: bool = False
    ) -> CommandPlan:
        self.capabilities.require("custom_slots", now)
        if not opt_in:
            raise ValueError("persistent slot configuration requires explicit opt-in")
        if isinstance(slot, bool) or not isinstance(slot, int) or not 1 <= slot <= 255:
            raise ValueError("slot must be an integer in 1..255")
        if position is None:
            command = f"M891 T{slot}"
        else:
            if len(position) != 3:
                raise ValueError("XYZ coordinates required")
            axes = {axis.name: axis for axis in self.capabilities.axes}
            if any(name not in axes or not axes[name].contains(value) for name, value in zip("XYZ", position)):
                raise ValueError("slot outside verified machine travel limits")
            command = f"M890 T{slot} " + " ".join(f"{name}{value:g}" for name, value in zip("XYZ", position))
        return CommandPlan((command, "M889"), "custom_slots", "persistent configuration", "slot readback")

    def feed_override(self, percent: float, now: float, instant: bool = False) -> CommandPlan:
        self.capabilities.require("feed_override", now)
        if instant:
            self.capabilities.require("instant_override", now)
        low, high = (
            (10, 300)
            if self.capabilities.features.get("instant_override", CapabilityEvidence()).permits(now)
            else (50, 200)
        )
        if not math.isfinite(percent) or not low <= percent <= high:
            raise ValueError(f"override must be {low}..{high}%")
        return CommandPlan(
            (f"{'$F' if instant else 'M220'} S{percent:g}",), "feed_override", "feed override", "override telemetry"
        )

    def named_io(self, name: str, enabled: bool, now: float, power: float = 100) -> CommandPlan:
        self.capabilities.require("named_io", now)
        if not math.isfinite(power) or not 0 < power <= 100:
            raise ValueError("power must be 0..100 (exclusive zero)")
        mappings = {
            "air": ("M7", "M9"),
            "light": ("M821", "M822"),
            "vacuum": (f"M801 S{power:g}", "M802"),
            "external": (f"M851 S{power:g}", "M852"),
        }
        if name not in mappings:
            raise ValueError("unmapped named output")
        return CommandPlan((mappings[name][0 if enabled else 1],), "named_io", "accessory output")


class AckState(str, Enum):
    PLANNED = "planned"
    SENT = "sent"
    ACCEPTED = "accepted"
    VERIFIED = "verified"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"


@dataclass
class CommandLifecycle:
    command_id: str
    plan: CommandPlan
    state: AckState = AckState.PLANNED
    sent_at: float | None = None
    acknowledged_at: float | None = None
    receipt: str = ""

    def sent(self, now: float) -> None:
        if self.state != AckState.PLANNED:
            raise ValueError("command already dispatched")
        if not math.isfinite(now):
            raise ValueError("invalid timestamp")
        self.sent_at, self.state = now, AckState.SENT

    def acknowledge(self, now: float, receipt: str, accepted: bool = True) -> None:
        if self.state != AckState.SENT or self.sent_at is None or not math.isfinite(now) or now < self.sent_at:
            raise ValueError("invalid acknowledgment transition")
        if not receipt:
            raise ValueError("receipt required")
        self.acknowledged_at, self.receipt = now, receipt
        self.state = AckState.ACCEPTED if accepted else AckState.REJECTED

    @property
    def latency_ms(self) -> float | None:
        return (
            None
            if self.sent_at is None or self.acknowledged_at is None
            else (self.acknowledged_at - self.sent_at) * 1000
        )

    def verify(self, readback: str) -> None:
        if self.state != AckState.ACCEPTED or not readback:
            raise ValueError("accepted command and independent readback required")
        self.receipt += "\nreadback:" + readback
        self.state = AckState.VERIFIED

    def expire(self, now: float, timeout: float) -> bool:
        if not math.isfinite(timeout) or timeout <= 0 or not math.isfinite(now):
            raise ValueError("invalid timeout")
        if self.state == AckState.SENT and self.sent_at is not None and now - self.sent_at >= timeout:
            self.state = AckState.TIMED_OUT
            return True
        return False


def linuxcnc_declaration(
    machine_id: str, axes: tuple[AxisDefinition, ...], topology: str = "cartesian"
) -> CapabilitySet:
    """Offline declaration only. No LinuxCNC transport/execution is implemented."""
    return CapabilitySet(machine_id, backend="linuxcnc", axes=axes, topology=topology, execution_available=False)


@dataclass(frozen=True)
class ToolSlot:
    number: int
    position: tuple[float, float, float]


def parse_slot_readback(response: str) -> tuple[ToolSlot, ...]:
    """Parse M889 response from community v2.1.0c ATCHandler.cpp.

    An empty or truncated response cannot establish absence of slots. Caller
    must collect the full response through its command boundary before parsing.
    """
    if "Tool Slots Configuration:" not in response or re.search(r"(?im)^error", response):
        raise ValueError("missing or failed M889 slot response")
    slots = []
    for line in response.splitlines():
        if not line.startswith("Tool ") or line == "Tool Slots Configuration:":
            continue
        match = re.fullmatch(r"Tool (\d+): X=([-+\d.eE]+) Y=([-+\d.eE]+) Z=([-+\d.eE]+)", line.strip())
        if not match:
            raise ValueError("malformed slot readback")
        number = int(match.group(1))
        position = (float(match.group(2)), float(match.group(3)), float(match.group(4)))
        if not 0 <= number <= 255 or any(not math.isfinite(value) for value in position):
            raise ValueError("invalid slot readback")
        slots.append(ToolSlot(number, position))
    if not slots or len({slot.number for slot in slots}) != len(slots):
        raise ValueError("empty or duplicate slot readback")
    return tuple(slots)
