"""One-packet machine pose evidence; offsets and TLO remain separate values."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import cos, isfinite, radians, sin
from typing import Protocol

Vec3 = tuple[float, float, float]


class MachineTransform(Protocol):
    def machine_point(self, point: Sequence[float]) -> Sequence[float]: ...


@dataclass(frozen=True)
class ObservedPose:
    timestamp: float
    state: str
    machine_mm: Vec3
    work_mm: Vec3
    tool: int | None
    tool_length_mm: float | None
    rotation_deg: float = 0
    wcs_index: int | None = None
    rotary_deg: float = 0

    def __post_init__(self) -> None:
        for point in (self.machine_mm, self.work_mm):
            if len(point) != 3 or not all(isfinite(v) for v in point):
                raise ValueError("Pose requires three finite coordinates")
        values: tuple[float, ...] = (self.timestamp, self.rotation_deg, self.rotary_deg)
        if self.tool_length_mm is not None:
            values += (self.tool_length_mm,)
        if not all(isfinite(v) for v in values):
            raise ValueError("Pose values must be finite")

    @classmethod
    def from_packet(cls, state: str, fields: Mapping[str, Sequence[float]], timestamp: float) -> ObservedPose:
        machine, work = fields.get("MPos"), fields.get("WPos")
        if not machine or not work or len(machine) < 3 or len(work) < 3:
            raise ValueError("Packet is missing MPos or WPos")
        modes = fields.get("C", ())
        if len(modes) < 3 or modes[2] not in (0, 1):
            raise ValueError("Packet units unavailable; millimeter pose cannot be established")
        factor = 25.4 if modes[2] else 1.0
        tool = fields.get("T", [])
        source = fields.get("SE")
        if source and not int(source[6]) & 8:
            tool = []
        rotation = fields.get("R", [0])[0]
        wcs = fields.get("G", [])
        return cls(
            timestamp,
            state,
            (machine[0] * factor, machine[1] * factor, machine[2] * factor),
            (work[0] * factor, work[1] * factor, work[2] * factor),
            int(tool[0]) if tool else None,
            tool[1] if len(tool) > 1 else None,
            rotation,
            int(wcs[0]) if wcs else None,
            machine[3] if len(machine) > 3 else 0,
        )

    def fresh(self, now: float, max_age: float = 0.8) -> bool:
        return isfinite(now) and 0 <= now - self.timestamp <= max_age

    @property
    def reported_offset_mm(self) -> Vec3:
        angle = radians(self.rotation_deg)
        x, y, z = self.work_mm
        rotated = (cos(angle) * x - sin(angle) * y, sin(angle) * x + cos(angle) * y, z)
        return (
            self.machine_mm[0] - rotated[0],
            self.machine_mm[1] - rotated[1],
            self.machine_mm[2] - rotated[2],
        )

    def preview_delta_mm(self, setup: MachineTransform, preview_program_point: Sequence[float]) -> tuple[float, ...]:
        preview_machine = setup.machine_point(preview_program_point)
        return tuple(a - b for a, b in zip(self.machine_mm, preview_machine))
