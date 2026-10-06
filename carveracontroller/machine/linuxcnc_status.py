"""Read-only LinuxCNC NML observations for commissioning and backend bring-up.

Uses linuxcnc.stat().poll(), never a command or HAL writer. Raw joint units
are retained separately from Cartesian units; no joint-to-axis mapping is assumed.
https://linuxcnc.org/docs/stable/html/config/python-interface.html
"""

from __future__ import annotations

import importlib
import math
from dataclasses import asdict, dataclass
from typing import Any, cast


def finite(value: object) -> float:
    if type(value) not in (float, int):
        raise ValueError("status number must be finite")
    try:
        result = float(cast("float | int", value))
    except OverflowError as exc:
        raise ValueError("status number must be finite") from exc
    if not math.isfinite(result):
        raise ValueError("status number must be finite")
    return result


def integer(value: object) -> int:
    if type(value) is not int:
        raise ValueError("status integer required")
    return value


def flag(value: object) -> bool:
    if type(value) not in (bool, int) or value not in (0, 1):
        raise ValueError("status flag must be 0 or 1")
    return bool(value)


@dataclass(frozen=True)
class JointObservation:
    index: int
    kind: str
    units_per_mm_or_degree: float
    commanded: float
    actual: float
    following_error: float
    velocity: float
    homed: bool
    homing: bool
    enabled: bool
    fault: bool
    min_hard_limit: bool
    max_hard_limit: bool
    min_soft_limit: bool
    max_soft_limit: bool


@dataclass(frozen=True)
class StatusObservation:
    machine_id: str
    observed_at: float
    sequence: int
    generation: int
    ini_filename: str
    axis_mask: int
    linear_units_per_mm: float
    angular_units_per_degree: float
    actual_position: tuple[float, ...]
    joints: tuple[JointObservation, ...]
    digital_inputs: tuple[bool, ...]
    digital_outputs: tuple[bool, ...]
    analog_inputs: tuple[float, ...]
    analog_outputs: tuple[float, ...]
    task_state: int
    task_mode: int
    interp_state: int
    motion_mode: int
    execution_state: int
    tool_in_spindle: int

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "backend": "linuxcnc", "evidence": "NML status poll", **asdict(self)}


@dataclass(frozen=True)
class SignalTransition:
    signal: str
    previous: bool
    current: bool
    previous_observed_at: float
    observed_at: float


class LinuxCNCStatusReader:
    """Explicitly connect on a LinuxCNC host; polling belongs off the UI thread.

    A failed poll invalidates last/freshness and breaks transition continuity.
    Transitions represent sample changes, not exact machine-side event times.
    """

    def __init__(self, machine_id: str, status: Any):
        if not isinstance(machine_id, str) or not machine_id.strip():
            raise ValueError("machine identity required")
        self.machine_id = machine_id
        self.status = status
        self.last: StatusObservation | None = None
        self.transitions: tuple[SignalTransition, ...] = ()
        self.sequence = 0
        self.generation = 0

    @classmethod
    def connect_local(cls, machine_id: str) -> LinuxCNCStatusReader:
        module = importlib.import_module("linuxcnc")
        return cls(machine_id, module.stat())

    def poll(self, now: float) -> StatusObservation:
        try:
            now = finite(now)
            if now < 0 or (self.last is not None and now < self.last.observed_at):
                raise ValueError("observation clock regressed")
            self.status.poll()
            s = self.status
            count = integer(s.joints)
            if not 0 <= count <= 64 or len(s.joint) < count:
                raise ValueError("incomplete joint status")
            joints = []
            for index, raw in enumerate(s.joint[:count]):
                kind = integer(raw["jointType"])
                if kind not in (1, 2):
                    raise ValueError("unknown joint type")
                units = finite(raw["units"])
                if units <= 0:
                    raise ValueError("positive joint units required")
                joints.append(
                    JointObservation(
                        index,
                        "linear" if kind == 1 else "angular",
                        units,
                        finite(raw["output"]),
                        finite(raw["input"]),
                        finite(raw["ferror_current"]),
                        finite(raw["velocity"]),
                        *(
                            flag(raw[key])
                            for key in (
                                "homed",
                                "homing",
                                "enabled",
                                "fault",
                                "min_hard_limit",
                                "max_hard_limit",
                                "min_soft_limit",
                                "max_soft_limit",
                            )
                        ),
                    )
                )
            pose = tuple(finite(value) for value in s.actual_position)
            mask = integer(s.axis_mask)
            linear, angular = finite(s.linear_units), finite(s.angular_units)
            if len(pose) != 9 or not 0 <= mask <= 511 or linear <= 0 or angular <= 0:
                raise ValueError("invalid Cartesian frame or units")
            if not isinstance(s.ini_filename, str) or not s.ini_filename:
                raise ValueError("observed INI path required")
            observation = StatusObservation(
                self.machine_id,
                now,
                self.sequence + 1,
                self.generation,
                s.ini_filename,
                mask,
                linear,
                angular,
                pose,
                tuple(joints),
                tuple(flag(v) for v in s.din),
                tuple(flag(v) for v in s.dout),
                tuple(finite(v) for v in s.ain),
                tuple(finite(v) for v in s.aout),
                *(
                    integer(getattr(s, name))
                    for name in (
                        "task_state",
                        "task_mode",
                        "interp_state",
                        "motion_mode",
                        "exec_state",
                        "tool_in_spindle",
                    )
                ),
            )
        except Exception:
            self.last = None
            self.transitions = ()
            self.generation += 1
            raise
        previous = self.last
        changes = []
        compatible = (
            previous is not None
            and previous.ini_filename == observation.ini_filename
            and previous.axis_mask == observation.axis_mask
            and len(previous.joints) == len(observation.joints)
            and tuple((j.kind, j.units_per_mm_or_degree) for j in previous.joints)
            == tuple((j.kind, j.units_per_mm_or_degree) for j in observation.joints)
            and len(previous.digital_inputs) == len(observation.digital_inputs)
            and len(previous.digital_outputs) == len(observation.digital_outputs)
        )
        if compatible:
            assert previous is not None
            for prefix, old, new in (
                ("din", previous.digital_inputs, observation.digital_inputs),
                ("dout", previous.digital_outputs, observation.digital_outputs),
            ):
                for index, (a, b) in enumerate(zip(old, new)):
                    if a != b:
                        changes.append(SignalTransition(f"{prefix}.{index}", a, b, previous.observed_at, now))
            for old_joint, new_joint in zip(previous.joints, observation.joints):
                for name in (
                    "homed",
                    "homing",
                    "enabled",
                    "fault",
                    "min_hard_limit",
                    "max_hard_limit",
                    "min_soft_limit",
                    "max_soft_limit",
                ):
                    a, b = getattr(old_joint, name), getattr(new_joint, name)
                    if a != b:
                        changes.append(
                            SignalTransition(f"joint.{new_joint.index}.{name}", a, b, previous.observed_at, now)
                        )
        self.transitions = tuple(changes)
        self.sequence = observation.sequence
        self.last = observation
        return observation

    def fresh(self, now: float, max_age: float = 1.0) -> bool:
        now, max_age = finite(now), finite(max_age)
        if max_age <= 0:
            raise ValueError("positive maximum age required")
        return self.last is not None and 0 <= now - self.last.observed_at <= max_age
