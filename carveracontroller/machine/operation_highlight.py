"""Map inclusive operation source lines to the viewer's interpolated vertex IDs.

The line-strip labels a motion with its destination source line. Include the
preceding vertex so the first selected motion is complete, including arc samples
and duplicate vertices inserted for move-type transitions. No geometry is copied.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections.abc import Sequence


def operation_vertex_span(lines: Sequence[int], start: int, end: int) -> tuple[float, float] | None:
    if isinstance(start, bool) or isinstance(end, bool) or not isinstance(start, int) or not isinstance(end, int):
        raise ValueError("Operation source lines must be integers")
    if start < 1 or end < start:
        raise ValueError("Operation source span must be positive and ordered")
    left, right = bisect_left(lines, start), bisect_right(lines, end)
    if left == right or right < 2:
        return None
    # MeshManager encodes the position-array offset: 2, 5, 8, ... .
    return (float(3 * max(0, left - 1) + 2), float(3 * (right - 1) + 2))
