"""Bounded, captured program inspection; never loads or executes a job."""

import hashlib
from dataclasses import dataclass
from pathlib import Path

from .program_operations import FrameMotionBounds, ProgramOperations


@dataclass(frozen=True)
class ProgramPreview:
    digest: str
    units: tuple[str, ...]
    frames: tuple[str, ...]
    tool_ids: tuple[int, ...]
    operation_names: tuple[str, ...]
    unresolved_lines: tuple[int, ...]
    segments: tuple
    line_count: int
    warnings: tuple[str, ...]
    excerpt: str
    active_tool_ids: tuple[int, ...] = ()
    six_pocket_banks: tuple = ()
    frame_bounds: tuple[FrameMotionBounds, ...] = ()
    frame_previews: tuple = ()


def inspect_program(path, *, byte_limit=1048576, line_limit=5000):
    """Inspect complete captured bytes, or decline instead of summarizing a prefix."""
    with Path(path).open("rb") as source:
        content = source.read(byte_limit + 1)
    if len(content) > byte_limit:
        raise ValueError(f"Quick inspection limit: {byte_limit:,} bytes. Load a local preview for this larger program.")
    text = content.decode("utf-8", errors="strict")
    if len(text.splitlines()) > line_limit:
        raise ValueError(f"Quick inspection limit: {line_limit:,} lines. Load a local preview for this larger program.")
    program = ProgramOperations.from_text(text, max_arc_segments=64)
    states = [checkpoint.state for checkpoint in program.checkpoints]
    tools = sorted({tool for state in states for tool in (state.tool, state.pending_tool) if tool is not None})
    warnings = tuple(dict.fromkeys(warning for op in program.operations for warning in op.warnings))
    segments = program.motion_segments
    # Sample entire source extent; disconnected segments remain disconnected.
    stride = max(1, (len(segments) + 1999) // 2000)
    sampled = segments[::stride]
    if segments and sampled[-1] is not segments[-1]:
        sampled += (segments[-1],)
    frame_previews = []
    for extent in program.frame_bounds:
        frame_segments = tuple(segment for segment in segments if segment.wcs == extent.wcs)
        step = max(1, (len(frame_segments) + 1999) // 2000)
        preview = frame_segments[::step]
        if frame_segments and preview[-1] is not frame_segments[-1]:
            preview += (frame_segments[-1],)
        frame_previews.append((extent.wcs, preview))
    return ProgramPreview(
        hashlib.sha256(content).hexdigest(),
        tuple(sorted({state.units for state in states if state.units is not None})),
        tuple(sorted({state.wcs for state in states if state.wcs is not None})),
        tuple(tools),
        tuple(op.name for op in program.operations),
        program.unresolved_motion_lines,
        tuple(sampled),
        len(program.lines),
        warnings,
        "\n".join(program.lines[:24]) + ("\n…" if len(program.lines) > 24 else ""),
        tuple(sorted({state.tool for state in states if state.tool is not None})),
        tuple(bank for bank in program.plan_tool_banks(6) if bank.slots),
        program.frame_bounds,
        tuple(frame_previews),
    )
