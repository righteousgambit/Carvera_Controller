"""One-packet machine pose evidence; offsets and TLO remain separate values."""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, radians, sin


@dataclass(frozen=True)
class ObservedPose:
    timestamp: float
    state: str
    machine_mm: tuple
    work_mm: tuple
    tool: int | None
    tool_length_mm: float | None
    rotation_deg: float = 0
    wcs_index: int | None = None
    rotary_deg: float = 0

    def __post_init__(self):
        for point in (self.machine_mm, self.work_mm):
            if len(point) != 3 or not all(isfinite(v) for v in point):
                raise ValueError("Pose requires three finite coordinates")
        values = (self.timestamp, self.rotation_deg, self.rotary_deg)
        if self.tool_length_mm is not None:
            values += (self.tool_length_mm,)
        if not all(isfinite(v) for v in values):
            raise ValueError("Pose values must be finite")

    @classmethod
    def from_packet(cls, state, fields, timestamp):
        machine, work = fields.get("MPos"), fields.get("WPos")
        if not machine or not work or len(machine) < 3 or len(work) < 3:
            raise ValueError("Packet is missing MPos or WPos")
        tool = fields.get("T", [])
        rotation = fields.get("R", [0])[0]
        wcs = fields.get("G", [])
        return cls(
            timestamp,
            state,
            tuple(machine[:3]),
            tuple(work[:3]),
            int(tool[0]) if tool else None,
            tool[1] if len(tool) > 1 else None,
            rotation,
            int(wcs[0]) if wcs else None,
            machine[3] if len(machine) > 3 else 0,
        )

    def fresh(self, now, max_age=0.8):
        return isfinite(now) and 0 <= now - self.timestamp <= max_age

    @property
    def reported_offset_mm(self):
        angle = radians(self.rotation_deg)
        x, y, z = self.work_mm
        rotated = (cos(angle) * x - sin(angle) * y, sin(angle) * x + cos(angle) * y, z)
        return tuple(a - b for a, b in zip(self.machine_mm, rotated))

    def preview_delta_mm(self, setup, preview_program_point):
        preview_machine = setup.machine_point(preview_program_point)
        return tuple(a - b for a, b in zip(self.machine_mm, preview_machine))
