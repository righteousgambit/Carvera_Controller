"""Bounded M889 coordinate receipt. Pocket contents are never inferred."""

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

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


class SlotInventory:
    def __init__(self):
        self.reset()

    def reset(self):
        self.receipt = None
        self.pending = False
        self.error = "Not queried"
        self.lines = []
        self.started_at = None
        self.generation = None
        self.source = ()

    def begin(self, generation, now, source=None):
        if self.pending:
            raise ValueError("A slot query is already pending")
        self.reset()
        self.pending = True
        self.error = "Awaiting M889 header and complete response"
        self.generation, self.started_at = generation, now
        self.source = tuple(sorted((str(k), str(v)) for k, v in (source or {}).items()))

    def fail(self, reason):
        self.pending = False
        self.lines = []
        self.error = reason

    def expire(self, generation, now):
        if self.generation is not None and generation != self.generation:
            self.reset()
        elif self.pending and not 0 <= now - self.started_at < 5:
            self.fail("Slot readback timed out; no complete receipt")

    def feed(self, line, generation, now):
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


def inventory_rows(receipt, declared):
    """Join logical controller numbers, without asserting physical occupancy."""
    slots = {slot.number: slot.position for slot in receipt.slots} if receipt else {}
    return tuple(
        {
            "number": number,
            "position": slots.get(number),
            "declared_name": getattr(declared.get(number), "description", "") or "",
            "declared": number in declared,
            "contents": "Unknown",
        }
        for number in sorted(
            n
            for n in slots.keys() | declared.keys()
            if isinstance(n, int) and not isinstance(n, bool) and 0 <= n <= 255
        )
    )
