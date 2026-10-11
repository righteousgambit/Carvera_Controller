"""Indexed source explanations and search; no transport or physical-pose inference."""

from __future__ import annotations

import re
from bisect import bisect_left, bisect_right
from dataclasses import dataclass

from .program_operations import ModalState, MotionSegment, Operation, ProgramOperations


@dataclass(frozen=True)
class MoveExplanation:
    line_number: int
    source: str
    operation: Operation | None
    before: ModalState
    after: ModalState
    segments: tuple[MotionSegment, ...]
    unresolved: bool
    warnings: tuple[str, ...]
    context: tuple[tuple[int, str], ...]
    program_hash: str

    @property
    def feed_description(self) -> str:
        state = self.after
        if state.feed is None or state.feed_mode is None:
            return "Feed unknown"
        if state.feed_mode == "G93":
            code = re.sub(r"\([^()]*\)|;.*", "", self.source)
            if self.segments and not re.search(r"(?i)F\s*[+-]?(?:\d|\.)", code):
                return "G93 · feed missing on this move; duration unknown"
            return f"G93 · {state.feed:g} inverse minutes"
        if state.units is None:
            return f"{state.feed_mode} · units unknown"
        value = state.feed * (25.4 if state.units == "G20" else 1)
        unit = "mm/min" if state.feed_mode == "G94" else "mm/rev"
        return f"{state.feed_mode} · {value:g} {unit}"


class MoveInspector:
    """Indexes built once per program; explanation cost scales with one move."""

    def __init__(self, program: ProgramOperations):
        self.program = program
        self._segment_lines = tuple(s.line_number for s in program.motion_segments)
        self._motion_lines = tuple(sorted(set(self._segment_lines) | set(program.unresolved_motion_lines)))
        self._operation_starts = tuple(op.start_line for op in program.operations)
        self._unresolved = frozenset(program.unresolved_motion_lines)
        self._warnings: dict[int, list[str]] = {}
        for operation in program.operations:
            for warning in operation.warnings:
                match = re.match(r"Line (\d+):", warning)
                if match:
                    self._warnings.setdefault(int(match[1]), []).append(warning)
                else:
                    span = re.match(r"Lines (\d+)–(\d+):", warning)
                    if span:
                        for line in range(max(1, int(span[1])), min(len(program.lines), int(span[2])) + 1):
                            self._warnings.setdefault(line, []).append(warning)

    def explain(self, line_number: int) -> MoveExplanation:
        if (
            isinstance(line_number, bool)
            or not isinstance(line_number, int)
            or not 1 <= line_number <= len(self.program.lines)
        ):
            raise ValueError("Choose a source line within this program")
        before = self.program.checkpoints[line_number - 2].state if line_number > 1 else ModalState()
        after = self.program.checkpoints[line_number - 1].state
        index = bisect_right(self._operation_starts, line_number) - 1
        operation = self.program.operations[index] if index >= 0 else None
        if operation and line_number > operation.end_line:
            operation = None
        lo, hi = bisect_left(self._segment_lines, line_number), bisect_right(self._segment_lines, line_number)
        warnings = list(self._warnings.get(line_number, ()))
        if before.recovery_errors:
            warnings.append("Inherited uncertainty: " + "; ".join(before.recovery_errors))
        warnings.extend(
            error for error in after.recovery_errors if error not in before.recovery_errors and error not in warnings
        )
        if lo != hi and after.wcs is None:
            warnings.append("Work coordinate frame unknown; geometry is unregistered")
        return MoveExplanation(
            line_number,
            self.program.lines[line_number - 1],
            operation,
            before,
            after,
            self.program.motion_segments[lo:hi],
            line_number in self._unresolved,
            tuple(dict.fromkeys(warnings)),
            tuple(
                (n, self.program.lines[n - 1])
                for n in range(max(1, line_number - 2), min(len(self.program.lines), line_number + 2) + 1)
            ),
            self.program.file_hash,
        )

    def adjacent_motion(self, line_number: int, direction: int) -> int | None:
        if direction not in (-1, 1):
            raise ValueError("Direction must be -1 or 1")
        index = (
            bisect_right(self._motion_lines, line_number)
            if direction == 1
            else bisect_left(self._motion_lines, line_number) - 1
        )
        return self._motion_lines[index] if 0 <= index < len(self._motion_lines) else None

    def search(self, query: str, limit: int = 100) -> tuple[int, ...]:
        """AND filters: rapid, cutting, unresolved, tool:T17; other words match source/operation.

        Results include source/state lines for text queries; tool and motion filters
        operate on parsed motion only, never a comment containing a tool number.
        """
        if not 1 <= limit <= 500:
            raise ValueError("Search result limit must be 1..500")
        terms = query.casefold().split()
        if not terms:
            return ()
        results = []
        for number, source in enumerate(self.program.lines, 1):
            lo, hi = bisect_left(self._segment_lines, number), bisect_right(self._segment_lines, number)
            segments = self.program.motion_segments[lo:hi]
            motion = bool(segments) or number in self._unresolved
            state = self.program.checkpoints[number - 1].state
            index = bisect_right(self._operation_starts, number) - 1
            operation = self.program.operations[index].name if index >= 0 else ""
            haystack = (source + " " + operation).casefold()
            matched = True
            for term in terms:
                if term == "rapid":
                    ok = any(s.rapid for s in segments)
                elif term == "cutting":
                    ok = any(s.cutting for s in segments)
                elif term == "unresolved":
                    ok = number in self._unresolved
                elif term.startswith("tool:"):
                    tool = re.fullmatch(r"tool:t?(\d+)", term)
                    ok = bool(tool and motion and state.tool == int(tool[1]))
                else:
                    ok = term in haystack
                matched &= ok
            if matched:
                results.append(number)
                if len(results) == limit:
                    break
        return tuple(results)
