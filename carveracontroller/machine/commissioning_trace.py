"""Bounded historical joint traces; no interpolation across status changes."""

from __future__ import annotations

from dataclasses import dataclass

from carveracontroller.machine.linuxcnc_status import StatusObservation

TRACE_METRICS = ("Command / feedback", "Following error", "Velocity")
TRACE_PAGE = 200


@dataclass(frozen=True)
class TracePoint:
    sample: int
    elapsed: float
    values: tuple[float, ...]


@dataclass(frozen=True)
class JointTrace:
    first: int
    last: int
    total: int
    names: tuple[str, ...]
    unit: str
    points: tuple[TracePoint, ...]
    segments: tuple[tuple[int, int], ...]


def joint_trace(observations: tuple[StatusObservation, ...], cursor: int, joint_index: int, metric: str) -> JointTrace:
    if metric not in TRACE_METRICS or type(cursor) is not int or type(joint_index) is not int:
        raise ValueError("Valid trace selection required")
    names = ("Commanded", "Actual") if metric == TRACE_METRICS[0] else (metric,)
    if not observations:
        return JointTrace(0, 0, 0, names, "", (), ())
    cursor = max(0, min(cursor, len(observations) - 1))
    first = (cursor // TRACE_PAGE) * TRACE_PAGE
    last = min(first + TRACE_PAGE, len(observations))
    selected = next((joint for joint in observations[cursor].joints if joint.index == joint_index), None)
    if selected is None:
        return JointTrace(first, last, len(observations), names, "", (), ())
    # Raw joint values are plotted only in the selected joint's declared units.
    unit = f"raw units ({selected.units_per_mm_or_degree:g} per {'mm' if selected.kind == 'linear' else 'degree'})"
    if metric == "Velocity":
        unit += "/s"
    points: list[TracePoint] = []
    segments: list[tuple[int, int]] = []
    previous_key: object = None
    previous_sample = -2
    previous_time = -1.0
    for index in range(first, last):
        observation = observations[index]
        joint = next((item for item in observation.joints if item.index == joint_index), None)
        if joint is None or (joint.kind, joint.units_per_mm_or_degree) != (
            selected.kind,
            selected.units_per_mm_or_degree,
        ):
            previous_key = None
            previous_sample = -2
            continue
        key = (
            observation.machine_id,
            observation.ini_filename,
            observation.generation,
            observation.axis_mask,
            observation.linear_units_per_mm,
            observation.angular_units_per_degree,
            tuple((item.index, item.kind, item.units_per_mm_or_degree) for item in observation.joints),
        )
        values = (
            (joint.commanded, joint.actual)
            if metric == TRACE_METRICS[0]
            else (joint.following_error,)
            if metric == "Following error"
            else (joint.velocity,)
        )
        points.append(TracePoint(index, observation.observed_at - observations[0].observed_at, values))
        if index == previous_sample + 1 and key == previous_key and observation.observed_at > previous_time:
            segments.append((len(points) - 2, len(points) - 1))
        previous_key, previous_sample, previous_time = key, index, observation.observed_at
    return JointTrace(first, last, len(observations), names, unit, tuple(points), tuple(segments))
