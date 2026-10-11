"""Detached C1 viewer geometry mapped to the same nominal chassis kinematics."""

from __future__ import annotations

import math
from collections.abc import Callable, Iterator, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, dataclass, replace
from types import MappingProxyType
from typing import Any

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.addons.machine_simulation.profile import CAD_HEAD, CAD_OFFSET, GROUPS, MachineProfile
from carveracontroller.addons.machine_simulation.workholding import placed_point
from carveracontroller.addons.manufacturing_simulation import SweptTool, Vec3
from carveracontroller.addons.tool_visualization.tool_definition import ToolDefinition
from carveracontroller.machine.geometry_changes import (
    GeometryContext,
    asset_problems,
    digest_context,
    verify_context_assets,
)
from carveracontroller.machine.repeat_parts import RepeatPartPlan, StockInstance
from carveracontroller.machine.simulation_preview import simulation_tools


@dataclass(frozen=True)
class SceneClearanceCapture:
    profile: MachineProfile
    components: Mapping[str, MachineProfile]
    setup: MachineSetup
    placement: tuple[tuple[float, float, float], float, float]
    definition: ToolDefinition
    number: int
    repeat_plan: RepeatPartPlan | None
    context: GeometryContext
    digest: str


def capture_scene_clearance(
    profile: MachineProfile | None,
    components: Mapping[str, MachineProfile],
    setup: MachineSetup,
    placement: tuple[tuple[float, float, float], float, float],
    definition: ToolDefinition,
    number: int,
    repeat_plan: RepeatPartPlan | None,
    context: GeometryContext,
) -> SceneClearanceCapture:
    if profile is None or not profile.model.startswith("Carvera C1"):
        raise ValueError("Load a Carvera C1 CAD profile before capturing its nominal kinematics")
    if type(number) is not int or definition.number != number:
        raise ValueError("Select an explicit loaded tool profile")
    if setup.stock_size_mm is None and repeat_plan is None:
        raise ValueError("Declare stock dimensions and placement in Scene first")
    # Keep only the selected assembly's asset checks; unrelated loaded tools do
    # not participate. Everything else is detached by capture_context upstream.
    context = deepcopy(context)
    context["tools"] = {str(number): context["tools"].get(str(number))}
    if context["tools"][str(number)] is None:
        raise ValueError("The selected tool profile is absent from the captured scene")
    selected = {group: components.get(group, profile) for group in sorted(GROUPS)}
    binding = {
        "geometry": {group: value.geometry_sha256 for group, value in selected.items()},
        "context": context,
        "tool_number": number,
        "setup": setup.record(),
        "placement": placement,
        "definition": {**asdict(definition), "tool_type": definition.tool_type.value},
        "repeat_plan": repeat_plan.to_dict() if repeat_plan is not None else None,
    }
    return SceneClearanceCapture(
        profile,
        MappingProxyType(selected),
        setup,
        placement,
        replace(definition),
        number,
        repeat_plan,
        context,
        digest_context(binding),
    )


def validate_scene_source(source: object) -> None:
    if not isinstance(source, dict) or set(source) != {"kind", "scene_digest", "tool_number", "geometry", "notes"}:
        raise ValueError("Scene source needs kind, scene_digest, tool_number, geometry and notes")
    if source["kind"] != "C1 nominal component envelopes" or type(source["tool_number"]) is not int:
        raise ValueError("Unsupported scene source or tool identity")
    geometry = source["geometry"]
    if not isinstance(geometry, dict) or set(geometry) != GROUPS:
        raise ValueError("Scene source must retain every selected CAD group identity")
    for digest in [source["scene_digest"], *geometry.values()]:
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Scene source identities must be SHA256 values")
    notes = source["notes"]
    if not isinstance(notes, list) or len(notes) > 16 or any(not isinstance(n, str) or len(n) > 512 for n in notes):
        raise ValueError("Scene source notes exceed the bounded format")


def component_frame(group: str) -> tuple[str, int]:
    return (
        ("world", 0)
        if group == "fixed"
        else ("tool", 1 if group == "carriage" else 2)
        if group in ("carriage", "spindle")
        else ("work", 1)
    )


def component_points(
    capture: SceneClearanceCapture,
    group: str,
    profile: MachineProfile,
    component: Mapping[str, Any],
    length: float,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> Iterator[tuple[float, float, float]]:
    """Same registered vertices for conservative bodies and triangle surfaces."""
    hx, hy, hz = (CAD_HEAD[i] + CAD_OFFSET[i] for i in range(3))
    values = component["vertices"]
    frame, _count = component_frame(group)
    shift, angle, jaw = capture.placement
    radians = math.radians(angle)
    placed_offset = tuple(CAD_OFFSET[i] + shift[i] for i in range(3))
    cosine, sine = math.cos(radians), math.sin(radians)
    movable = component.get("workholding_role", component.get("role")) == "movable"
    for offset in range(0, len(values), 10):
        if offset % 1280 == 0 and cancelled():
            raise InterruptedError("Scene component preparation cancelled")
        if group == "workholding":
            point = placed_point(
                values[offset : offset + 3],
                profile.workholding_pivot_mm,
                placed_offset,
                cosine,
                sine,
                jaw if movable else 0,
            )
        else:
            point = (
                values[offset] + CAD_OFFSET[0],
                values[offset + 1] + CAD_OFFSET[1],
                values[offset + 2] + CAD_OFFSET[2],
            )
        if frame == "tool":
            point = (point[0] - hx, point[1] - hy, point[2] + (length - hz if group == "spindle" else 0))
        yield point


def build_scene_clearance(
    capture: SceneClearanceCapture,
    *,
    cancelled: Callable[[], bool] = lambda: False,
) -> dict[str, Any]:
    """Prepare per-component conservative boxes on a worker, never read the UI.

    CAD offset/head and Y-table conventions exactly match MachineProfile.pose.
    X/Z are machine coordinates; tool-chain origin is the selected tool tip.
    Carriage excludes Z travel, spindle includes the selected stickout, and all
    bed-mounted components (including ATC) follow negative machine Y. Hidden
    groups remain included. No pair is silently excluded or geometry truncated.
    """

    def check() -> None:
        if cancelled():
            raise InterruptedError("Scene clearance capture cancelled")

    def verify() -> None:
        problems = asset_problems(verify_context_assets(capture.context, cancelled=cancelled))
        if problems:
            raise ValueError("\n".join(problems))

    check()
    verify()
    tool = simulation_tools({capture.number: capture.definition}, {str(capture.number)})[str(capture.number)]
    length = tool.overall_length_mm
    hy = CAD_HEAD[1] + CAD_OFFSET[1]
    bodies: list[dict[str, object]] = []

    def add(name: str, frame: str, count: int, low: Sequence[float], high: Sequence[float]) -> None:
        check()
        if len(bodies) >= 32:
            raise ValueError("Scene requires more than 32 body envelopes; no components were omitted")
        # Planar CAD surfaces still need a conservative positive-thickness box.
        upper = [max(high[i], low[i] + 0.001) for i in range(3)]
        bodies.append(
            {"name": name[:80], "frame": frame, "joint_count": count, "minimum_mm": tuple(low), "maximum_mm": upper}
        )

    for group, profile in capture.components.items():
        for index, component in enumerate(profile.components):
            check()
            if component["group"] != group:
                continue
            low, high = [float("inf")] * 3, [float("-inf")] * 3
            frame, count = component_frame(group)
            for point in component_points(capture, group, profile, component, length, cancelled=cancelled):
                for axis in range(3):
                    low[axis], high[axis] = min(low[axis], point[axis]), max(high[axis], point[axis])
            title = str(component.get("assembly", group)).replace("\n", " ")
            add(f"{group} {index + 1} · {title}", frame, count, low, high)
    if capture.repeat_plan is not None:
        stocks = capture.repeat_plan.parts
    else:
        size = capture.setup.stock_size_mm
        assert size is not None
        stocks = (
            StockInstance(
                "Current stock",
                "G54",
                capture.setup.work_offset_mm,
                capture.setup.stock_origin_mm,
                size,
                stock_orientation_deg=capture.setup.stock_orientation.degrees,
            ),
        )
    for part in stocks:
        add(f"stock {part.wcs} · {part.name}", "work", 1, *part.bounds)
    zero = Vec3(0, 0, 0)
    sections = SweptTool(zero, zero, tool).sections()
    for name in ("cutter", "shank", "holder"):
        selected = [section for section in sections if section.component == name]
        if selected:
            radius = max(section.radius_mm for section in selected)
            add(
                f"T{capture.number} {name}",
                "tool",
                2,
                (-radius, -radius, min(s.low_mm for s in selected)),
                (radius, radius, max(s.high_mm for s in selected)),
            )
    notes = [
        "Per-component conservative boxes include hidden CAD; open spaces and curved surfaces may produce false alarms.",
        "Initial bounding stock includes imported voids and material already removed; cutting contact is not automatically excluded.",
        "No mounted pair is excluded automatically. Review intentional mounting contact explicitly.",
        "Nominal C1 CAD/head registration and published travel only; no measured origin, installed assembly or physical clearance qualification.",
        *tool.clearance_notes,
    ]
    if not any(section.component == "holder" for section in sections):
        notes.append("No holder envelope declared; complete tool assembly clearance remains unknown.")
    record: dict[str, Any] = {
        "schema": 1,
        "name": f"C1 scene · T{capture.number} · {capture.digest[:12]}",
        "tool_chain": [
            {"name": "X", "kind": "linear", "axis": [1, 0, 0], "minimum": -360, "maximum": 0},
            {"name": "Z", "kind": "linear", "axis": [0, 0, 1], "minimum": -140, "maximum": 0},
        ],
        "work_chain": [{"name": "Y", "kind": "linear", "axis": [0, -1, 0], "minimum": -240, "maximum": 0}],
        "tool_base": {"translation": [0, hy, 0]},
        "work_base": {"translation": [0, hy, 0]},
        "collision_bodies": bodies,
        "collision_exclusions": [],
        "scene_source": {
            "kind": "C1 nominal component envelopes",
            "scene_digest": capture.digest,
            "tool_number": capture.number,
            "geometry": {g: p.geometry_sha256 for g, p in capture.components.items()},
            "notes": notes,
        },
    }
    from carveracontroller.machine.kinematic_review import machine_from_record

    machine_from_record(record)
    verify()
    check()
    return record
