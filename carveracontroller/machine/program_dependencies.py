"""Captured program requirements against local declarations, never run readiness."""

from dataclasses import dataclass

from .program_preview import ProgramPreview


@dataclass(frozen=True)
class ProgramDependencies:
    digest: str
    missing_tools: tuple[int, ...]
    text: str


def describe_dependencies(
    program: ProgramPreview,
    *,
    available_tools=(),
    profile_name="",
    toolset_name="",
    stock_size_mm=None,
    alignment_confirmed=False,
):
    """Use this candidate's IDs, never the currently loaded CAM program's IDs.

    Definition presence does not establish usable geometry, physical inventory,
    pocket identity or measurement. Six-pocket banks are explicit Carvera drafts.
    """
    missing = tuple(tool for tool in program.tool_ids if tool not in available_tools)
    active = ", ".join(f"T{tool}" for tool in program.active_tool_ids) or "None resolved"
    pending = tuple(tool for tool in program.tool_ids if tool not in program.active_tool_ids)
    lines = [
        "Selected program · setup dependencies",
        f"Machine profile: {profile_name or 'Not selected'}",
        f"Toolset declaration: {toolset_name or 'None loaded'}",
        f"Active parsed tools: {active}",
    ]
    if pending:
        lines.append("Preselected only: " + ", ".join(f"T{tool}" for tool in pending))
    lines.append("Missing preview definitions: " + (", ".join(f"T{tool}" for tool in missing) or "None"))
    if program.six_pocket_banks:
        lines.append(f"Six-pocket Carvera draft: {len(program.six_pocket_banks)} tool banks")
        for bank in program.six_pocket_banks[:8]:
            assignment = ", ".join(f"P{slot}: T{tool}" for slot, tool in bank.slots)
            lines.append(f"Bank {bank.index} · lines {bank.start_line}–{bank.end_line}: {assignment}")
        if len(program.six_pocket_banks) > 8:
            lines.append("Further banks omitted here; load local preview to review the complete sequence.")
        if len(program.six_pocket_banks) > 1:
            lines.append("Bank swaps require reviewed stop, physical loading and tool measurement; source unchanged.")
    else:
        lines.append("No active tool-bank sequence resolved.")
    lines.append("Work frames: " + (", ".join(program.frames) or "Unknown"))
    if len(program.frames) > 1:
        lines.append("Each work frame needs its own registered transform; a single preview offset is insufficient.")
    lines.append(
        "Stock declaration: "
        + (" × ".join(f"{value:g}" for value in stock_size_mm) + " mm" if stock_size_mm else "Missing")
    )
    lines.append("Preview alignment: " + ("Confirmed locally" if alignment_confirmed else "Not confirmed"))
    lines.append(
        f"Unresolved motion: {len(program.unresolved_lines)} lines"
        + ("; interpreter review required." if program.unresolved_lines else ".")
    )
    lines.append("Local declarations only · physical tools, offsets, travel and clearance remain unchecked.")
    return ProgramDependencies(program.digest, missing, "\n".join(lines))
