"""Bounded M889 coordinate receipt. Pocket contents are never inferred."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal, Protocol, TypedDict

from .capabilities import ToolSlot, parse_slot_readback


@dataclass(frozen=True)
class SlotReceipt:
    generation: int
    observed_at: float
    slots: tuple[ToolSlot, ...]
    response_sha256: str
    response: str = ""
    completed_at: str = ""
    source: tuple[tuple[str, str], ...] = ()


class DeclaredTool(Protocol):
    @property
    def description(self) -> str: ...


class InventoryRow(TypedDict):
    number: int
    position: tuple[float, float, float] | None
    declared_name: str
    declared: bool
    contents: Literal["Unknown"]


class SlotInventory:
    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.receipt: SlotReceipt | None = None
        self.pending = False
        self.error = "Not queried"
        self.lines: list[str] = []
        self.started_at: float | None = None
        self.generation: int | None = None
        self.source: tuple[tuple[str, str], ...] = ()

    def begin(self, generation: int, now: float, source: Mapping[str, object] | None = None) -> None:
        if self.pending:
            raise ValueError("A slot query is already pending")
        self.reset()
        self.pending = True
        self.error = "Awaiting M889 header and complete response"
        self.generation, self.started_at = generation, now
        self.source = tuple(sorted((str(k), str(v)) for k, v in (source or {}).items()))

    def fail(self, reason: str) -> None:
        self.pending = False
        self.lines = []
        self.error = reason

    def expire(self, generation: int, now: float) -> None:
        if self.generation is not None and generation != self.generation:
            self.reset()
        elif self.pending and (self.started_at is None or not 0 <= now - self.started_at < 5):
            self.fail("Slot readback timed out; no complete receipt")

    def feed(self, line: str, generation: int, now: float) -> None:
        self.expire(generation, now)
        if not self.pending:
            return
        line = line.strip()
        if line.lower().startswith(("error", "alarm")):
            self.fail("Controller reported an error during slot readback")
        elif line == "Tool Slots Configuration:":
            if self.lines:
                self.fail("Repeated slot header; response is ambiguous")
            else:
                self.lines.append(line)
        elif self.lines and line.lower() == "ok":
            response = "\n".join(self.lines)
            try:
                slots = parse_slot_readback(response)
            except ValueError as exc:
                self.fail(str(exc))
                return
            self.receipt = SlotReceipt(
                generation,
                now,
                slots,
                hashlib.sha256(response.encode()).hexdigest(),
                response,
                datetime.now(timezone.utc).isoformat(),
                self.source,
            )
            self.pending = False
            self.error = ""
            self.lines = []
        elif self.lines and line.startswith("Tool "):
            if len(self.lines) >= 257 or len(line) > 256:
                self.fail("Slot response exceeded its bounded size")
            else:
                self.lines.append(line)
        elif self.lines and line and not line.startswith(("<", "{", "#")):
            self.fail("Interleaved output; slot response cannot be attributed")


def inventory_rows(receipt: SlotReceipt | None, declared: Mapping[int, DeclaredTool]) -> tuple[InventoryRow, ...]:
    """Join logical controller numbers, without asserting physical occupancy."""
    slots = {slot.number: slot.position for slot in receipt.slots} if receipt else {}
    rows: list[InventoryRow] = []
    for number in sorted(
        n for n in slots.keys() | declared.keys() if isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 255
    ):
        tool = declared.get(number)
        rows.append(
            {
                "number": number,
                "position": slots.get(number),
                "declared_name": getattr(tool, "description", "") or "",
                "declared": number in declared,
                "contents": "Unknown",
            }
        )
    return tuple(rows)
