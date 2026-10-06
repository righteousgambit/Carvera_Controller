"""Compile inspectable bank bodies, not authorized machine execution packages.

Carvera fixed-pocket drafts defer T selection until M6 and map logical tools to
the explicitly planned pockets. Approach, stop/retract and calibrated offsets
remain separate backend transactions. No command is sent by this module.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .program_operations import ProgramOperations, ToolBank

_WORD = re.compile(r"([A-Za-z])\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))")


def _code(raw: str) -> str:
    """Mask comments, retaining spans for surgical source edits."""
    result, depth = [], 0
    for character in raw:
        if character == ";" and not depth:
            result.extend(" " * (len(raw) - len(result)))
            break
        if character == "(":
            depth += 1
            result.append(" ")
        elif character == ")":
            depth -= 1
            if depth < 0:
                raise ValueError("Unbalanced comment")
            result.append(" ")
        else:
            result.append(" " if depth else character)
    if depth:
        raise ValueError("Unbalanced comment")
    return "".join(result)


@dataclass(frozen=True)
class BankLine:
    source_line: int
    original: str
    draft: str
    reason: str = ""


@dataclass(frozen=True)
class BankProgramDraft:
    program_hash: str
    bank_index: int
    source_range: tuple[int, int]
    mapping: tuple[tuple[int, int], ...]  # logical tool, controller tool/pocket
    lines: tuple[BankLine, ...]
    inherited_state: dict[str, object]
    modal_restoration: tuple[str, ...]
    errors: tuple[str, ...]
    cautions: tuple[str, ...]
    offset_mode: str

    @property
    def body(self) -> str:
        return "\n".join(line.draft for line in self.lines) if not self.errors else ""

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = json.loads(json.dumps(asdict(self), allow_nan=False))
        value.update(schema=1, kind="carvera-bank-program-draft", execution_available=False)
        value["compiled_body"] = self.body
        value["draft_sha256"] = hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return value


def compile_bank(program: ProgramOperations, bank: ToolBank, *, offset_mode: str = "automatic") -> BankProgramDraft:
    """Produce a source-linked draft; never claim standalone/re-entry safety.

    ``logical_h`` is an explicit convention that H indexes match logical T
    numbers. Automatic mode refuses G43/H, rather than assuming that convention.
    Tool preselection is removed and made explicit on each M6, including when
    its T word precedes the bank boundary. Comments and every other word survive.
    """
    if offset_mode not in ("automatic", "logical_h"):
        raise ValueError("Unknown offset convention")
    candidates = program.plan_tool_banks(6)
    if bank not in candidates:
        raise ValueError("Bank does not belong to this program's six-pocket plan")
    mapping = {tool: pocket for pocket, tool in bank.slots}
    errors, output = [], []
    if any(tool <= 0 or tool >= 999990 for tool in mapping):
        errors.append("Probe, empty-spindle and special tools need separate backend classification")
    if len(mapping) != len(bank.slots) or any(not 1 <= p <= 6 for p in mapping.values()):
        errors.append("Draft requires unique logical tools in six fixed pockets")
    for number in range(bank.start_line, bank.end_line + 1):
        raw = program.lines[number - 1]
        try:
            code = _code(raw)
            if code.strip() in ("", "%"):
                output.append(BankLine(number, raw, raw))
                continue
            matches = list(_WORD.finditer(code))
            residue = _WORD.sub("", code).strip()
            if residue or any(m[1].upper() not in "NGMXYZIJKRPFSTH" for m in matches):
                raise ValueError("Expressions, conditional blocks, macros or unsupported words cannot be remapped")
            words = {}
            for match in matches:
                letter, value = match[1].upper(), float(match[2])
                if not math.isfinite(value):
                    raise ValueError("Non-finite word")
                if letter not in ("G", "M") and letter in words:
                    raise ValueError(f"Duplicate {letter} word")
                words.setdefault(letter, []).append(value)
            ms = words.get("M", [])
            gs = words.get("G", [])
            state = program.checkpoints[number - 1].state
            if state.recovery_errors:
                raise ValueError(state.recovery_errors[-1])
            if 6 in ms and (len(ms) != 1 or any(a in words for a in "XYZIJKR") or gs):
                raise ValueError("M6 must occupy a separate tool-change block")
            if "T" in words and (words["T"][0] < 0 or not words["T"][0].is_integer()):
                raise ValueError("Tool selection must be a nonnegative integer")
            if "H" in words:
                logical = words["H"][0]
                if offset_mode != "logical_h" or 43 not in gs:
                    raise ValueError("H offsets require explicit logical-H convention and G43")
                if not logical.is_integer() or int(logical) not in mapping or int(logical) != state.tool:
                    raise ValueError("H offset must match the active logical tool in this bank")
            edits, reasons = [], []
            for match in matches:
                if match[1].upper() == "T":
                    edits.append((match.start(), match.end(), ""))
                    reasons.append("Tool preselection deferred to M6")
                elif match[1].upper() == "H":
                    edits.append((match.start(), match.end(), f"H{mapping[int(float(match[2]))]}"))
                    reasons.append("Logical H mapped to controller offset")
            if 6 in ms:
                if state.tool not in mapping:
                    raise ValueError("Tool-change identity is unavailable in this bank")
                match = next(m for m in matches if m[1].upper() == "M" and float(m[2]) == 6)
                edits.append((match.start(), match.end(), f"T{mapping[state.tool]} {match[0]}"))
                reasons.append(f"Logical T{state.tool} maps to controller T{mapping[state.tool]}")
            draft = raw
            for start, end, replacement in sorted(edits, reverse=True):
                draft = draft[:start] + replacement + draft[end:]
            output.append(BankLine(number, raw, draft, "; ".join(dict.fromkeys(reasons))))
        except ValueError as exc:
            output.append(BankLine(number, raw, "", f"Cannot compile: {exc}"))
            errors.append(f"Line {number}: {exc}")
    before = program.checkpoints[bank.start_line - 2].state if bank.start_line > 1 else None
    inherited = asdict(before) if before else {}
    restoration, cautions = (
        [],
        [
            "Draft only: no verified stop/retract, physical reload, measurement or offset application",
            "Controller-tool measurements must be reconciled with this bank's logical-tool mapping",
            "Spindle restart and collision-qualified approach/re-entry are not generated",
        ],
    )
    if before:
        for name in ("units", "plane", "feed_mode", "wcs", "arc_distance"):
            value = getattr(before, name)
            if value:
                restoration.append(value)
            else:
                cautions.append(f"Inherited {name.replace('_', ' ')} is unknown")
        if before.feed is not None:
            restoration.append(f"F{before.feed:g}")
        if before.distance:
            restoration.append(before.distance)
        if before.motion is not None:
            cautions.append(f"Inherited G{before.motion} motion must be restored only with a reviewed approach")
        if before.spindle in ("M3", "M4"):
            cautions.append(f"Source inherits {before.spindle} S{before.spindle_speed}; spindle restart is omitted")
        if before.coolant and before.coolant != "M9":
            cautions.append(f"Source inherits {before.coolant}; accessory restart is omitted")
    return BankProgramDraft(
        program.file_hash,
        bank.index,
        (bank.start_line, bank.end_line),
        tuple(mapping.items()),
        tuple(output),
        inherited,
        tuple(restoration),
        tuple(dict.fromkeys(errors)),
        tuple(cautions),
        offset_mode,
    )


def save_draft(path: Path, draft: BankProgramDraft) -> None:
    """Exclusive creation preserves any existing file; exports JSON, never .nc."""
    data = json.dumps(draft.to_dict(), indent=2, allow_nan=False).encode()
    with Path(path).open("xb") as stream:
        stream.write(data)
