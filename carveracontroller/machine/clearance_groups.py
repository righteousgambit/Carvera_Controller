"""Group captured contact causes without discarding source motions or geometry.

This is report organization only. Identical conservative captures do not prove
physical contact, and missing capture/tool/operation identities remain separate.
"""

from bisect import bisect_right
from dataclasses import dataclass


@dataclass(frozen=True)
class ClearanceCause:
    key: tuple
    operation: str
    tools: tuple[str, ...]
    component: str
    obstacle: str
    method: str
    candidates: tuple


def group_clearance_candidates(candidates, *, contacts=(), segments=(), operations=()):
    captures = {}
    for line, contact in contacts:
        bounds = contact.obstacle_bounds
        signature = (contact.method, bounds.minimum.tuple, bounds.maximum.tuple, contact.sections)
        captures.setdefault((line, contact.component, contact.obstacle), {})[signature] = contact.method
    tools = {}
    for segment in segments:
        tools.setdefault(segment.line, set()).add(str(segment.tool_id))
    ordered = sorted(operations, key=lambda operation: operation.start_line)
    starts = [operation.start_line for operation in ordered]
    groups = {}
    metadata = {}
    for candidate in dict.fromkeys(candidates):
        line, component, obstacle = candidate
        index = bisect_right(starts, line) - 1
        operation = ordered[index] if index >= 0 and line <= ordered[index].end_line else None
        operation_key = (
            (operation.id, operation.start_line, operation.end_line)
            if operation is not None
            else ("unresolved operation", line)
        )
        tool_ids = tuple(sorted(tools.get(line, ())))
        tool_key = tool_ids or ("unresolved tool", line)
        signatures = captures.get(candidate) or {("missing capture", line): "Capture unavailable"}
        for geometry_key, method in signatures.items():
            key = (operation_key, tool_key, component, obstacle, geometry_key)
            groups.setdefault(key, []).append(candidate)
            metadata[key] = (operation.name if operation else "Unassigned operation", tool_ids, method)
    return tuple(
        ClearanceCause(key, metadata[key][0], metadata[key][1], key[2], key[3], metadata[key][2], tuple(motions))
        for key, motions in groups.items()
    )
