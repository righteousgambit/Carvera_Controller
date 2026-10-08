"""Inspectable declared rigid frame composition, independent of machine transport."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from carveracontroller.addons.manufacturing_simulation.kinematics import Transform
from carveracontroller.machine.coordinate_review import FramePath, FrameReview
from carveracontroller.machine.kinematic_review import machine_from_record, number, profile_digest


def transform_text(transform: Transform) -> str:
    rotation = transform.rotation
    rows = [" ".join(f"{value:.6g}" for value in rotation[index : index + 3]) for index in (0, 3, 6)]
    return f"Translation {transform.translation.tuple} mm; row-major rotation [{'; '.join(rows)}]"


def declared_frame_paths(
    record: object, positions: Mapping[str, float], tool_length_mm: float
) -> tuple[FramePath, ...]:
    """Explain ordered parent-local joints and final inverse-work composition.

    Origins are declared world coordinates; rows retain both local and cumulative
    transforms. A length offset appears only in tip derivations. Out-of-limit
    declarations remain visible diagnostics, never machine permission.
    """
    machine = machine_from_record(record)
    state = {name: number(value) for name, value in positions.items()}
    length = number(tool_length_mm)
    pose = machine.forward(state, length)
    source = f"Declared profile {profile_digest(record)}; not measured or controller-qualified"
    paths = []
    for title, base, joints in (
        ("Tool", machine.tool_base, machine.tool_chain),
        ("Workpiece", machine.work_base, machine.work_chain),
    ):
        group = f"Declared {title.lower()} chain"
        parent = f"{title} base"
        world = base
        paths.append(
            FramePath(
                FrameReview(parent, base.translation.tuple, source, transform_text(base)),
                None,
                group,
                "Declared world reference",
            )
        )
        for index, joint in enumerate(joints, 1):
            value = state[joint.name]
            local = joint.transform(value)
            world = world.compose(local)
            name = f"{title} joint {index} · {joint.name}"
            unit = "mm" if joint.kind == "linear" else "deg"
            status = "within declared limits" if joint.minimum <= value <= joint.maximum else "OUTSIDE declared limits"
            relation = (
                f"{joint.kind} {value:g} {unit}; axis {joint.axis.tuple} and pivot {joint.pivot.tuple} mm in parent frame. "
                f"Limits [{joint.minimum:g}, {joint.maximum:g}] {unit}: {status}.\n"
                f"Local: {transform_text(local)}\nCumulative = parent · local: {transform_text(world)}"
            )
            paths.append(
                FramePath(
                    FrameReview(
                        name,
                        world.translation.tuple,
                        source,
                        relation,
                        f"{value:g} {unit} · world origin {world.translation.tuple} mm",
                    ),
                    parent,
                    group,
                    "Ordered rigid composition",
                )
            )
            parent = name
    group = "Derived declared tool/workpiece relation"
    paths.append(
        FramePath(
            FrameReview(
                "Final tool world reference", pose.tool_world.translation.tuple, source, transform_text(pose.tool_world)
            ),
            None,
            group,
            "Final tool-chain reference",
        )
    )
    paths.append(
        FramePath(
            FrameReview(
                "Tool relative to workpiece",
                pose.tool_in_work.translation.tuple,
                source,
                f"Inverse(final workpiece world) · final tool world. {transform_text(pose.tool_in_work)}",
            ),
            None,
            group,
            "Two-chain derivation",
        )
    )
    for name, point, explanation in (
        ("Tool tip in world", pose.tooltip_world, "Final tool world · (0, 0, −length)"),
        ("Tool tip in workpiece", pose.tooltip_work, "Tool relative to workpiece · (0, 0, −length)"),
    ):
        paths.append(
            FramePath(
                FrameReview(
                    name,
                    point.tuple,
                    source,
                    f"{explanation}; declared origin-to-tip length {length:g} mm applied once. No controller compensation or motion.",
                ),
                "Final tool world reference" if name == "Tool tip in world" else "Tool relative to workpiece",
                group,
                "Declared tip derivation",
            )
        )
    paths.append(
        FramePath(
            FrameReview(
                "Tool axis in workpiece",
                None,
                source,
                f"Unit direction {pose.axis_in_work.tuple}; direction only, not a millimetre point. "
                f"Limit violations: {', '.join(pose.limit_violations) or 'none in declared state'}. "
                "Registration, TCP, clearance and execution remain unqualified.",
                f"Unit axis {pose.axis_in_work.tuple} · dimensionless direction",
            ),
            "Tool relative to workpiece",
            group,
            "Declared orientation",
        )
    )
    return tuple(paths)


@dataclass(frozen=True)
class SpatialFrame:
    name: str
    parent: str | None
    chain: str
    origin_mm: tuple[float, float, float]
    rotation: tuple[float, ...]
    direction_only: bool = False


def declared_spatial_frames(
    record: object, positions: Mapping[str, float], tool_length_mm: float, reference: str = "World"
) -> tuple[SpatialFrame, ...]:
    """All glyphs in one explicit reference; lengths and orientations stay distinct."""
    if reference not in ("World", "Workpiece"):
        raise ValueError("Spatial reference must be World or Workpiece")
    machine = machine_from_record(record)
    state = {name: number(value) for name, value in positions.items()}
    length = number(tool_length_mm)
    pose = machine.forward(state, length)
    conversion = Transform() if reference == "World" else pose.work_world.inverse()
    result: list[SpatialFrame] = []

    def append(name: str, transform: Transform, parent: str | None, chain: str, direction: bool = False) -> None:
        converted = conversion.compose(transform)
        result.append(SpatialFrame(name, parent, chain, converted.translation.tuple, converted.rotation, direction))

    for title, base, joints in (
        ("Tool", machine.tool_base, machine.tool_chain),
        ("Workpiece", machine.work_base, machine.work_chain),
    ):
        parent = f"{title} base"
        world = base
        append(parent, world, None, title)
        for index, joint in enumerate(joints, 1):
            world = world.compose(joint.transform(state[joint.name]))
            name = f"{title} joint {index} · {joint.name}"
            append(name, world, parent, title)
            parent = name
    append("Final tool world reference", pose.tool_world, None, "Derived")
    append("Tool relative to workpiece", pose.tool_world, None, "Derived")
    tip_world = Transform(pose.tool_world.rotation, pose.tooltip_world)
    append("Tool tip in world", tip_world, "Final tool world reference", "Derived")
    append("Tool tip in workpiece", tip_world, "Tool relative to workpiece", "Derived")
    # Draw an orientation glyph at the spindle reference, never an additional tip.
    append("Tool axis in workpiece", pose.tool_world, "Tool relative to workpiece", "Derived", True)
    return tuple(result)
