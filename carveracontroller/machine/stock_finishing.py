"""Compare two intended-tip continuations from a verified detached stock state."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from math import prod
from types import MappingProxyType
from typing import Any

from carveracontroller.addons.manufacturing_simulation import StockVolume, SweptTool, Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope, CollisionContact
from carveracontroller.machine.program_joint_clearance import ProgramBodyClearance
from carveracontroller.machine.program_stock_evolution import MAX_CELL_WORK, StockEvolution
from carveracontroller.machine.program_stock_inspection import StockMoveState


@dataclass(frozen=True)
class FinishContact:
    line: int
    tool: int
    contact: CollisionContact


@dataclass(frozen=True)
class StockContinuation:
    remaining_mm3: float
    removed_mm3: float
    contacts: tuple[FinishContact, ...]
    retained_curve_lines: tuple[int, ...]
    final: Mapping[str, Any]


@dataclass(frozen=True)
class FinishingComparison:
    bindings: tuple[object, object, object]
    after_segment: int
    stock: str
    after_line: int
    end_line: int
    candidate_tool: int
    initial_mm3: float
    planned: StockContinuation
    candidate: StockContinuation
    extra_removed_mm3: float
    extra_remaining_mm3: float
    cell_work: int
    qualification: str = (
        "Same intended tip path and fixed axes, with planned tools or one substituted reviewed tool. "
        "Stock cell-center estimates only; empty cells do not prove clearance. "
        "Planned continuation is a comparison baseline, not a nominal finished-part target. "
        "Machine/fixture collisions, changed tool-length joint poses, cutting forces, ATC and physical execution "
        "are not recomputed or qualified. Uncertified curve sweeps retain material."
    )


def compare_stock_continuation(
    body: ProgramBodyClearance,
    evolution: StockEvolution,
    envelopes: Mapping[int, Mapping[str, Sequence[AxialEnvelope]]],
    state: StockMoveState,
    stock_name: str,
    candidate_tool: int,
    end_line: int | None = None,
    *,
    cancelled: Callable[[], bool] = lambda: False,
    max_cell_work: int = MAX_CELL_WORK,
) -> FinishingComparison:
    if any(saved is not current for saved, current in zip(state.bindings, (body, evolution, envelopes))):
        raise ValueError("Reconstructed stock belongs to a different retained review")
    end = body.end_line if end_line is None else end_line
    if (
        type(candidate_tool) is not int
        or candidate_tool not in evolution.inputs.tools
        or not isinstance(stock_name, str)
        or stock_name not in state.after
        or type(end) is not int
        or not state.line <= end <= body.end_line
        or type(max_cell_work) is not int
        or not 1 <= max_cell_work <= MAX_CELL_WORK
    ):
        raise ValueError("Choose a reviewed tool, reconstructed stock and retained continuation range")
    segments = tuple(s for s in body.segments[state.segment_index + 1 :] if s.line <= end)
    if not segments:
        raise ValueError("No resolved moves follow this stock state in the selected range")
    offset = Vec3(*evolution.inputs.stocks[stock_name][0])
    curved = set(body.curved_lines) | {line for line, _, error in body.curve_enclosures if error > 0}
    work = contacts_count = 0

    def run(substitute: bool) -> tuple[StockVolume, StockContinuation]:
        nonlocal work, contacts_count
        stock = StockVolume.from_snapshot(state.after[stock_name], cancelled=cancelled)
        initial = stock.remaining_volume_mm3
        contacts = []
        held = set()
        for segment in segments:
            if cancelled():
                raise InterruptedError("Finishing comparison cancelled; previous result retained")
            number = candidate_tool if substitute else int(segment.tool_id)
            sweep = SweptTool(
                segment.start - offset, segment.end - offset, evolution.inputs.tools[number], segment.axis
            )
            work += prod(stock.shape) * (len(sweep.sections()) + 1)
            if work > max_cell_work:
                raise ValueError("Finishing comparison exhausted shared cell-work budget; no partial comparison")
            uncertified = segment.line in curved
            if uncertified:
                held.add(segment.line)
            found = stock.collision_contacts(sweep, cutting=segment.cutting and not uncertified, cancelled=cancelled)
            contacts.extend(
                FinishContact(
                    segment.line,
                    number,
                    replace(
                        contact,
                        obstacle=stock_name,
                        source_ratio=(
                            segment.source_start_ratio
                            + (segment.source_end_ratio - segment.source_start_ratio) * contact.first_fraction
                            if contact.first_fraction is not None
                            else None
                        ),
                    ),
                )
                for contact in found
            )
            contacts_count += len(found)
            if contacts_count > 100_000:
                raise ValueError("Finishing comparison exceeds complete shared contact budget")
            if segment.cutting and not uncertified:
                stock.subtract(sweep, cancelled=cancelled)
        return stock, StockContinuation(
            stock.remaining_volume_mm3,
            initial - stock.remaining_volume_mm3,
            tuple(contacts),
            tuple(sorted(held)),
            MappingProxyType(stock.snapshot(cancelled=cancelled)),
        )

    planned_stock, planned = run(False)
    candidate_stock, candidate = run(True)
    work += prod(planned_stock.shape)
    if work > max_cell_work:
        raise ValueError("Finishing comparison exhausted shared cell-work budget; no partial comparison")
    more_removed = more_remaining = count = 0
    for z in range(planned_stock.shape[2]):
        for y in range(planned_stock.shape[1]):
            for x in range(planned_stock.shape[0]):
                if count % 128 == 0 and cancelled():
                    raise InterruptedError("Finishing comparison cancelled; previous result retained")
                has_planned, has_candidate = planned_stock.occupied(x, y, z), candidate_stock.occupied(x, y, z)
                more_removed += has_planned and not has_candidate
                more_remaining += has_candidate and not has_planned
                count += 1
    if cancelled():
        raise InterruptedError("Finishing comparison cancelled; previous result retained")
    return FinishingComparison(
        state.bindings,
        state.segment_index,
        stock_name,
        state.line,
        end,
        candidate_tool,
        planned.remaining_mm3 + planned.removed_mm3,
        planned,
        candidate,
        more_removed * planned_stock.cell_volume_mm3,
        more_remaining * planned_stock.cell_volume_mm3,
        work,
    )
