"""Group captured contact causes without discarding source motions or geometry.

This is report organization only. Identical conservative captures do not prove
physical contact, and missing capture/tool/operation identities remain separate.
"""

from __future__ import annotations

from bisect import bisect_right
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol, Union

from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope, CollisionContact

Candidate = tuple[int, str, str]
CaptureSignature = tuple[str, tuple[float, float, float], tuple[float, float, float], tuple[AxialEnvelope, ...]]
GeometryKey = Union[CaptureSignature, tuple[str, int]]
OperationKey = Union[tuple[str, int, int], tuple[str, int]]
ToolKey = Union[tuple[str, ...], tuple[str, int]]
CauseKey = tuple[OperationKey, ToolKey, str, str, GeometryKey]


class SourceOperation(Protocol):
    id: str
    name: str
    start_line: int
    end_line: int


class SourceSegment(Protocol):
    line: int
    tool_id: str


@dataclass(frozen=True)
class ClearanceCause:
    key: CauseKey
    operation: str
    tools: tuple[str, ...]
    component: str
    obstacle: str
    method: str
    candidates: tuple[Candidate, ...]


def group_clearance_candidates(
    candidates: Iterable[Candidate],
    *,
    contacts: Iterable[tuple[int, CollisionContact]] = (),
    segments: Iterable[SourceSegment] = (),
    operations: Iterable[SourceOperation] = (),
) -> tuple[ClearanceCause, ...]:
    captures: dict[Candidate, dict[GeometryKey, str]] = {}
    for line, contact in contacts:
        bounds = contact.obstacle_bounds
        signature = (contact.method, bounds.minimum.tuple, bounds.maximum.tuple, contact.sections)
        captures.setdefault((line, contact.component, contact.obstacle), {})[signature] = contact.method
    tools: dict[int, set[str]] = {}
    for segment in segments:
        tools.setdefault(segment.line, set()).add(str(segment.tool_id))
    ordered = sorted(operations, key=lambda operation: operation.start_line)
    starts = [operation.start_line for operation in ordered]
    groups: dict[CauseKey, list[Candidate]] = {}
    metadata: dict[CauseKey, tuple[str, tuple[str, ...], str]] = {}
    for candidate in dict.fromkeys(candidates):
        line, component, obstacle = candidate
        index = bisect_right(starts, line) - 1
        operation = ordered[index] if index >= 0 and line <= ordered[index].end_line else None
        operation_key: OperationKey = (
            (operation.id, operation.start_line, operation.end_line)
            if operation is not None
            else ("unresolved operation", line)
        )
        tool_ids = tuple(sorted(tools.get(line, ())))
        tool_key: ToolKey = tool_ids or ("unresolved tool", line)
        signatures = captures.get(candidate) or {("missing capture", line): "Capture unavailable"}
        for geometry_key, method in signatures.items():
            key: CauseKey = (operation_key, tool_key, component, obstacle, geometry_key)
            groups.setdefault(key, []).append(candidate)
            metadata[key] = (operation.name if operation else "Unassigned operation", tool_ids, method)
    return tuple(
        ClearanceCause(key, metadata[key][0], metadata[key][1], key[2], key[3], metadata[key][2], tuple(motions))
        for key, motions in groups.items()
    )
