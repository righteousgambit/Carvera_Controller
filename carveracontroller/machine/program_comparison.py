"""Compare immutable candidate captures without machine or filesystem access."""

from collections.abc import Iterable
from dataclasses import dataclass

from .program_preview import ProgramPreview


@dataclass(frozen=True)
class ProgramComparison:
    baseline_digest: str
    candidate_digest: str
    changed: bool
    text: str


def _items(values: Iterable[object]) -> str:
    items = tuple(values)
    return (
        ", ".join(str(value) for value in items[:16]) + (f" … ({len(items)} total)" if len(items) > 16 else "")
        or "None"
    )


def compare_programs(baseline: ProgramPreview, candidate: ProgramPreview) -> ProgramComparison:
    """Semantic summary, never a claim of equivalence or machining readiness."""
    changed = baseline.digest != candidate.digest
    lines = ["Captured bytes changed" if changed else "Identical captured bytes"]
    for name, before, after in (
        ("Units", baseline.units, candidate.units),
        ("Work frames", baseline.frames, candidate.frames),
        (
            "Active tools",
            tuple(f"T{t}" for t in baseline.active_tool_ids),
            tuple(f"T{t}" for t in candidate.active_tool_ids),
        ),
        ("Declared tools", tuple(f"T{t}" for t in baseline.tool_ids), tuple(f"T{t}" for t in candidate.tool_ids)),
        ("Operation sequence", baseline.operation_names, candidate.operation_names),
        ("Feed/spindle declarations", baseline.process_settings, candidate.process_settings),
        (
            "Six-pocket bank assignments",
            tuple(_items(f"P{p}: T{t}" for p, t in bank.slots) for bank in baseline.six_pocket_banks),
            tuple(_items(f"P{p}: T{t}" for p, t in bank.slots) for bank in candidate.six_pocket_banks),
        ),
    ):
        if before != after:
            lines.append(f"{name} changed\nBefore: {_items(before)}\nAfter: {_items(after)}")
    if baseline.line_count != candidate.line_count:
        lines.append(f"Source lines: {baseline.line_count} to {candidate.line_count}")
    before_bounds = {b.wcs: b for b in baseline.frame_bounds}
    after_bounds = {b.wcs: b for b in candidate.frame_bounds}
    for frame in sorted(set(before_bounds) | set(after_bounds), key=lambda key: key or ""):
        old, new = before_bounds.get(frame), after_bounds.get(frame)
        label = frame or "Unknown frame"
        if old is None or new is None:
            lines.append(f"{label}: resolved bounds {'added' if old is None else 'removed'}")
        elif (old.minimum_mm, old.maximum_mm) != (new.minimum_mm, new.maximum_mm):
            lines.append(f"{label}: resolved bounds changed (mm)")
            for axis, lo, hi, newlo, newhi in zip(
                "XYZ", old.minimum_mm, old.maximum_mm, new.minimum_mm, new.maximum_mm
            ):
                if (lo, hi) != (newlo, newhi):
                    lines.append(f"{axis}: {lo:.3f}…{hi:.3f} to {newlo:.3f}…{newhi:.3f}")
    lines.append(f"Unresolved motion lines: {len(baseline.unresolved_lines)} to {len(candidate.unresolved_lines)}")
    if changed and len(lines) == 2 and len(baseline.unresolved_lines) == len(candidate.unresolved_lines):
        lines.append("Summary fields match; other source changes remain unclassified.")
    lines.extend(
        (
            "Bounds exclude unresolved moves. Matching summaries do not prove equivalent execution or clearance.",
            f"Baseline SHA-256: {baseline.digest}",
            f"Candidate SHA-256: {candidate.digest}",
        )
    )
    return ProgramComparison(baseline.digest, candidate.digest, changed, "\n\n".join(lines))
