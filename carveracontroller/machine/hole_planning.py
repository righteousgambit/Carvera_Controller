"""Explicit hole/thread preparation plans. Programs are previews, not machine sends.

Thread dimensions are nominal cutting design inputs, not a tolerance-class or
thread-gauge qualification. A positive fit allowance increases internal diameter.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class ThreadSpec:
    name: str
    major_mm: float
    pitch_mm: float
    pilot_mm: float

    @property
    def basic_minor_mm(self) -> float:
        return self.major_mm - 1.082532 * self.pitch_mm

    @classmethod
    def named(cls, name: str) -> ThreadSpec:
        try:
            return THREAD_SPECS[name.upper().replace(" ", "")]
        except KeyError as error:
            raise ValueError("Unknown thread; choose an explicit supported specification") from error


THREAD_SPECS = {
    "#6-32": ThreadSpec("#6-32 UNC", 0.138 * 25.4, 25.4 / 32, 0.1065 * 25.4),
    "#8-32": ThreadSpec("#8-32 UNC", 0.164 * 25.4, 25.4 / 32, 0.136 * 25.4),
    "#10-24": ThreadSpec("#10-24 UNC", 0.190 * 25.4, 25.4 / 24, 0.1495 * 25.4),
    "1/4-20": ThreadSpec("1/4-20 UNC", 6.35, 1.27, 0.201 * 25.4),
    "1/4-28": ThreadSpec("1/4-28 UNF", 6.35, 25.4 / 28, 0.213 * 25.4),
    "M3": ThreadSpec("M3x0.5", 3, 0.5, 2.5),
    "M4": ThreadSpec("M4x0.7", 4, 0.7, 3.3),
    "M5": ThreadSpec("M5x0.8", 5, 0.8, 4.2),
    "M6": ThreadSpec("M6x1", 6, 1, 5),
}


def _finite(*values: float) -> None:
    if any(not math.isfinite(v) or abs(v) > 100000 for v in values):
        raise ValueError("All dimensional and process inputs must be finite and bounded")


@dataclass(frozen=True)
class Hole:
    x_mm: float
    y_mm: float
    depth_mm: float
    thread_depth_mm: float | None = None

    def __post_init__(self) -> None:
        _finite(self.x_mm, self.y_mm, self.depth_mm)
        if self.depth_mm <= 0 or (self.thread_depth_mm is not None and not 0 < self.thread_depth_mm <= self.depth_mm):
            raise ValueError("Hole and thread depths must be positive; thread cannot exceed hole")


@dataclass(frozen=True)
class HoleTool:
    number: int
    kind: str
    diameter_mm: float
    cutting_length_mm: float
    reach_mm: float
    tip_angle_deg: float = 118
    thread_pitch_mm: float | None = None

    def __post_init__(self) -> None:
        _finite(self.diameter_mm, self.cutting_length_mm, self.reach_mm, self.tip_angle_deg)
        if (
            self.kind not in {"spot", "drill", "bore", "chamfer", "threadmill", "tap"}
            or not isinstance(self.number, int)
            or not 1 <= self.number <= 255
        ):
            raise ValueError("Invalid tool kind or tool number")
        if (
            min(self.diameter_mm, self.cutting_length_mm, self.reach_mm) <= 0
            or self.reach_mm < self.cutting_length_mm
            or not 30 <= self.tip_angle_deg <= 150
        ):
            raise ValueError("Invalid tool reach, cutting length, diameter or tip angle")
        if self.thread_pitch_mm is not None:
            _finite(self.thread_pitch_mm)
            if self.thread_pitch_mm <= 0:
                raise ValueError("Thread-tool pitch must be positive")


@dataclass(frozen=True)
class HoleStage:
    name: str
    tool_number: int
    lines: tuple[str, ...]


@dataclass(frozen=True)
class HolePlan:
    stages: tuple[HoleStage, ...]
    clearance_z_mm: float
    wcs: str
    warnings: tuple[str, ...] = (
        "Preview only; verify workholding, datum, tool geometry, travel and thread fit before execution.",
    )

    def gcode(self) -> str:
        # Carvera uses incremental IJK, but its G91 handler also handles G91.1
        # as relative endpoint mode. Restore G90 on the next block, before any
        # motion, so both Carvera and standard modal interpreters agree.
        result = [
            "(HOLE WORKFLOW PREVIEW)",
            "G91.1",
            "G21 G90 G17 G94",
            self.wcs,
            f"G0 Z{self.clearance_z_mm:.5f}",
        ]
        for stage in self.stages:
            result.extend(
                (f"({stage.name})", "M5", f"T{stage.tool_number} M6", *stage.lines, f"G0 Z{self.clearance_z_mm:.5f}")
            )
        return "\n".join((*result, "M5", "M2")) + "\n"


@dataclass(frozen=True)
class HoleWorkflow:
    holes: tuple[Hole, ...]
    tools: dict[str, HoleTool]
    thread_spec: ThreadSpec
    clearance_z_mm: float
    top_z_mm: float
    floor_z_mm: float
    feed_mm_min: float
    plunge_feed_mm_min: float
    rpm: float
    fit_allowance_mm: float = 0
    radial_passes: int = 2
    handedness: str = "right"
    climb: bool = True
    chamfer_width_mm: float = 0.25
    bore_stepdown_mm: float = 0.5
    bottom_clearance_mm: float = 0.5
    wcs: str = "G54"

    def __post_init__(self) -> None:
        _finite(
            self.clearance_z_mm,
            self.top_z_mm,
            self.floor_z_mm,
            self.feed_mm_min,
            self.plunge_feed_mm_min,
            self.rpm,
            self.fit_allowance_mm,
            self.chamfer_width_mm,
            self.bore_stepdown_mm,
            self.bottom_clearance_mm,
            self.thread_spec.major_mm,
            self.thread_spec.pitch_mm,
            self.thread_spec.pilot_mm,
        )
        if (
            not self.holes
            or len(self.holes) > 1000
            or not 1 <= self.radial_passes <= 20
            or not isinstance(self.radial_passes, int)
        ):
            raise ValueError("Hole count and radial passes exceed bounded plan limits")
        if (
            self.clearance_z_mm <= self.top_z_mm
            or self.floor_z_mm >= self.top_z_mm
            or min(self.feed_mm_min, self.plunge_feed_mm_min) < 0.001
            or self.rpm < 1
            or self.bore_stepdown_mm <= 0
            or self.bottom_clearance_mm < 0
            or self.chamfer_width_mm < 0
        ):
            raise ValueError("Invalid clearance, floor or cutting parameters")
        if (
            self.handedness not in {"right", "left"}
            or self.wcs not in {f"G{i}" for i in range(54, 60)}
            or abs(self.fit_allowance_mm) > 0.1 * self.thread_spec.pitch_mm
        ):
            raise ValueError("Invalid handedness/WCS or excessive thread fit allowance")
        if not 0 < self.thread_spec.basic_minor_mm <= self.thread_spec.pilot_mm < self.thread_spec.major_mm:
            raise ValueError("Invalid thread specification diameters")
        if (
            any(key != tool.kind for key, tool in self.tools.items())
            or not {"drill", "threadmill"} <= self.tools.keys()
        ):
            raise ValueError("Matched drill and threadmill tools are required")
        if "bore" not in self.tools and abs(self.tools["drill"].diameter_mm - self.thread_spec.pilot_mm) > 0.025:
            raise ValueError("Pilot drill must match specified pilot diameter, or include a boring tool")
        if self.tools["drill"].diameter_mm > self.thread_spec.pilot_mm + 0.025:
            raise ValueError("Drill would remove thread material")
        for key in ("bore", "threadmill"):
            if key in self.tools and self.tools[key].diameter_mm >= self.tools["drill"].diameter_mm:
                raise ValueError("Milling cutter must clear the drilled pilot for axial entry")
        tool = self.tools["threadmill"]
        if tool.thread_pitch_mm is not None and abs(tool.thread_pitch_mm - self.thread_spec.pitch_mm) > 1e-6:
            raise ValueError("Multi-form threadmill pitch does not match thread")
        if (
            "chamfer" in self.tools
            and self.tools["chamfer"].diameter_mm < self.thread_spec.major_mm + 2 * self.chamfer_width_mm
        ):
            raise ValueError("Chamfer tool cannot reach requested mouth diameter")
        if (
            sum(
                math.ceil(h.depth_mm / self.bore_stepdown_mm)
                + math.ceil(
                    (h.thread_depth_mm if h.thread_depth_mm is not None else h.depth_mm - self.bottom_clearance_mm)
                    / self.thread_spec.pitch_mm
                )
                * self.radial_passes
                for h in self.holes
            )
            > 50000
        ):
            raise ValueError("Hole program exceeds motion budget")
        for hole in self.holes:
            drill = self.tools["drill"]
            tip_depth = drill.diameter_mm / (2 * math.tan(math.radians(drill.tip_angle_deg / 2)))
            if self.top_z_mm - hole.depth_mm - tip_depth < self.floor_z_mm:
                raise ValueError("Drill tip would cross declared floor clearance")
            if hole.depth_mm + tip_depth > min(drill.reach_mm, drill.cutting_length_mm):
                raise ValueError("Drill cutting length or reach is insufficient")
            thread_depth = (
                hole.thread_depth_mm if hole.thread_depth_mm is not None else hole.depth_mm - self.bottom_clearance_mm
            )
            if thread_depth <= 0 or thread_depth + self.bottom_clearance_mm > hole.depth_mm:
                raise ValueError("Blind thread requires bottom clearance below the thread")
            if thread_depth > tool.reach_mm or tool.cutting_length_mm < self.thread_spec.pitch_mm:
                raise ValueError("Threadmill reach or tooth engagement is insufficient")
            if "bore" in self.tools and hole.depth_mm > min(
                self.tools["bore"].reach_mm, self.tools["bore"].cutting_length_mm
            ):
                raise ValueError("Boring tool reach is insufficient")

    def _entry(self, hole: Hole) -> list[str]:
        return [f"G0 Z{self.clearance_z_mm:.5f}", f"G0 X{hole.x_mm:.5f} Y{hole.y_mm:.5f}"]

    def plan(self) -> HolePlan:
        stages = []
        for kind in ("spot", "drill", "bore", "chamfer", "threadmill"):
            if kind not in self.tools:
                continue
            tool = self.tools[kind]
            lines = [f"M3 S{self.rpm:.0f}", "G4 P3"]
            for hole in self.holes:
                lines.extend(self._entry(hole))
                if kind in {"spot", "drill", "chamfer"}:
                    if kind == "spot":
                        diameter = min(tool.diameter_mm, self.tools["drill"].diameter_mm / 2)
                        depth = diameter / (2 * math.tan(math.radians(tool.tip_angle_deg / 2)))
                    elif kind == "drill":
                        depth = hole.depth_mm + tool.diameter_mm / (2 * math.tan(math.radians(tool.tip_angle_deg / 2)))
                    else:
                        depth = (self.thread_spec.major_mm / 2 + self.chamfer_width_mm) / math.tan(
                            math.radians(tool.tip_angle_deg / 2)
                        )
                    if depth > min(tool.reach_mm, tool.cutting_length_mm) or self.top_z_mm - depth < self.floor_z_mm:
                        raise ValueError("Spot/chamfer/drill cutter cannot reach depth safely")
                    lines.append(f"G1 Z{self.top_z_mm - depth:.5f} F{self.plunge_feed_mm_min:.3f}")
                elif kind == "bore":
                    radius = (self.thread_spec.pilot_mm - tool.diameter_mm) / 2
                    lines.extend(
                        (
                            f"G1 Z{self.top_z_mm:.5f} F{self.plunge_feed_mm_min:.3f}",
                            f"G1 X{hole.x_mm + radius:.5f} F{self.feed_mm_min:.3f}",
                        )
                    )
                    levels = math.ceil(hole.depth_mm / self.bore_stepdown_mm)
                    for level in range(1, levels + 1):
                        z = self.top_z_mm - min(hole.depth_mm, level * self.bore_stepdown_mm)
                        lines.append(
                            f"G3 X{hole.x_mm + radius:.5f} Y{hole.y_mm:.5f} Z{z:.5f} I{-radius:.5f} J0 F{self.feed_mm_min:.3f}"
                        )
                    lines.append(f"G3 X{hole.x_mm + radius:.5f} Y{hole.y_mm:.5f} I{-radius:.5f} J0")
                    lines.append(f"G1 X{hole.x_mm:.5f} Y{hole.y_mm:.5f}")
                else:
                    depth = (
                        hole.thread_depth_mm
                        if hole.thread_depth_mm is not None
                        else hole.depth_mm - self.bottom_clearance_mm
                    )
                    final_radius = (self.thread_spec.major_mm + self.fit_allowance_mm - tool.diameter_mm) / 2
                    initial_radius = (self.thread_spec.pilot_mm - tool.diameter_mm) / 2
                    upward = self.climb
                    direction = "G3" if (self.handedness == "right") == upward else "G2"
                    for radial in range(1, self.radial_passes + 1):
                        radius = initial_radius + (final_radius - initial_radius) * radial / self.radial_passes
                        start_z = self.top_z_mm - depth if upward else self.top_z_mm
                        lines.extend(
                            (
                                f"G1 X{hole.x_mm:.5f} Y{hole.y_mm:.5f} F{self.feed_mm_min:.3f}",
                                f"G1 Z{start_z:.5f} F{self.plunge_feed_mm_min:.3f}",
                                f"G1 X{hole.x_mm + radius:.5f} F{self.feed_mm_min:.3f}",
                            )
                        )
                        travel = 0.0
                        x, y = hole.x_mm + radius, hole.y_mm
                        while travel < depth - 1e-9:
                            advance = min(self.thread_spec.pitch_mm, depth - travel)
                            travel += advance
                            angle = (1 if direction == "G3" else -1) * 2 * math.pi * travel / self.thread_spec.pitch_mm
                            nx, ny = hole.x_mm + radius * math.cos(angle), hole.y_mm + radius * math.sin(angle)
                            z = start_z + (travel if upward else -travel)
                            lines.append(
                                f"{direction} X{nx:.5f} Y{ny:.5f} Z{z:.5f} I{hole.x_mm - x:.5f} J{hole.y_mm - y:.5f} F{self.feed_mm_min:.3f}"
                            )
                            x, y = nx, ny
                        lines.append(f"G1 X{hole.x_mm:.5f} Y{hole.y_mm:.5f}")
                lines.append(f"G0 Z{self.clearance_z_mm:.5f}")
            stages.append(HoleStage(kind, tool.number, tuple(lines)))
        return HolePlan(tuple(stages), self.clearance_z_mm, self.wcs)

    def to_dict(self) -> dict[str, Any]:
        return {"version": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HoleWorkflow:
        values = dict(data)
        if values.pop("version", None) != 1:
            raise ValueError("Unsupported hole workflow version")
        values["holes"] = tuple(Hole(**h) for h in values["holes"])
        values["tools"] = {k: HoleTool(**t) for k, t in values["tools"].items()}
        values["thread_spec"] = ThreadSpec(**values["thread_spec"])
        return cls(**values)


@dataclass(frozen=True)
class TappingQualification:
    """Machine-specific physical qualification supplied by the backend owner.

    A supported command name alone is insufficient; synchronization, rigid
    reversal and an identified qualification receipt must all be asserted.
    """

    backend: str
    firmware_version: str
    receipt: str
    synchronized_spindle: bool
    rigid_reversal: bool
    cycles: tuple[str, ...]

    def require(self, handedness: str) -> str:
        cycle = "G84" if handedness == "right" else "G74"
        if (
            handedness not in {"right", "left"}
            or not self.backend
            or not self.firmware_version
            or not self.receipt
            or not self.synchronized_spindle
            or not self.rigid_reversal
            or cycle not in self.cycles
        ):
            raise ValueError("Tapping requires qualified spindle synchronization, reversal and explicit backend cycle")
        return cycle


def tapping_preview(
    holes: tuple[Hole, ...],
    tool: HoleTool,
    thread: ThreadSpec,
    qualification: TappingQualification | None,
    *,
    top_z_mm: float,
    clearance_z_mm: float,
    floor_z_mm: float,
    rpm: float,
    handedness: str = "right",
    wcs: str = "G54",
) -> str:
    """Generate declared qualified canned-cycle preview, never a device command.

    Prepared pilot geometry and tap/thread fit still require independent setup
    qualification. No community-controller tapping support is presumed.
    """
    if qualification is None:
        raise ValueError("No tapping qualification supplied")
    cycle = qualification.require(handedness)
    _finite(top_z_mm, clearance_z_mm, floor_z_mm, rpm, thread.pitch_mm)
    if tool.kind != "tap" or abs(tool.diameter_mm - thread.major_mm) > 0.01 or tool.thread_pitch_mm != thread.pitch_mm:
        raise ValueError("Tap must match selected major diameter and pitch")
    if (
        not holes
        or len(holes) > 1000
        or rpm < 1
        or clearance_z_mm <= top_z_mm
        or wcs not in {f"G{i}" for i in range(54, 60)}
    ):
        raise ValueError("Invalid tapping geometry, RPM or WCS")
    lines = [
        "(QUALIFIED BACKEND TAPPING PREVIEW)",
        "G21 G90 G17 G94",
        wcs,
        f"G0 Z{clearance_z_mm:.5f}",
        f"T{tool.number} M6",
        f"{'M3' if handedness == 'right' else 'M4'} S{round(rpm)}",
        "G4 P3",
    ]
    for hole in holes:
        if hole.thread_depth_mm is None:
            raise ValueError("Tapping requires explicit thread depth and bottom clearance")
        if (
            hole.thread_depth_mm >= hole.depth_mm
            or hole.thread_depth_mm > min(tool.cutting_length_mm, tool.reach_mm)
            or top_z_mm - hole.depth_mm < floor_z_mm
        ):
            raise ValueError("Tap depth/reach/floor exceeds prepared hole")
        lines.extend(
            (
                f"G0 X{hole.x_mm:.5f} Y{hole.y_mm:.5f}",
                f"{cycle} X{hole.x_mm:.5f} Y{hole.y_mm:.5f} Z{top_z_mm - hole.thread_depth_mm:.5f} R{clearance_z_mm:.5f} F{round(rpm) * thread.pitch_mm:.3f}",
                "G80",
                f"G0 Z{clearance_z_mm:.5f}",
            )
        )
    return "\n".join((*lines, "M5", "M2")) + "\n"
