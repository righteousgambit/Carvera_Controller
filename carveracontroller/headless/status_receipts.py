"""Bounded original status-event receipts; host IPC times are not firmware times."""

from __future__ import annotations

import hashlib
import math
from collections import deque
from copy import deepcopy
from typing import Any

from .telemetry import parse_status


class StatusReceipts:
    """Caller serializes access. Cursor reads never drain another consumer."""

    def __init__(self, capacity: int = 256) -> None:
        if type(capacity) is not int or not 2 <= capacity <= 4096:
            raise ValueError("Invalid status receipt capacity")
        self.items: deque[dict[str, Any]] = deque(maxlen=capacity)
        self.sequence = 0
        self.connection_id: str | None = None

    def observe(self, event: dict[str, Any], raw: bytes, now: float | None, utc: float) -> None:
        if event.get("event") == "connection":
            if type(event.get("connected")) is not bool:
                raise ValueError("Invalid connection event")
            identity = event.get("connection_id")
            if event["connected"] and (not isinstance(identity, str) or not 0 < len(identity) <= 100):
                raise ValueError("Connection event lacks identity")
            self.connection_id = identity if event["connected"] else None
        elif event.get("event") == "observation" and event.get("kind") == "status":
            if now is None or not math.isfinite(now) or now < 0 or not math.isfinite(utc) or utc < 0:
                raise ValueError("Status receipt clock unavailable")
            observation = event.get("observation")
            if not isinstance(observation, dict) or not isinstance(observation.get("raw"), str):
                raise ValueError("Invalid status event")
            # Preserve exactly the parser contract, including missing/unknown fields.
            if parse_status(observation["raw"]) != observation:
                raise ValueError("Status event does not match its original text")
            self.sequence += 1
            self.items.append(
                {
                    "sequence": self.sequence,
                    "connection_id": self.connection_id,
                    "received_at_s": now,
                    "received_utc_s": utc,
                    "ipc_sha256": hashlib.sha256(raw).hexdigest(),
                    "status": deepcopy(observation),
                }
            )

    def since(self, cursor: int) -> dict[str, Any]:
        if type(cursor) is not int or not 0 <= cursor <= self.sequence:
            raise ValueError("Invalid status receipt cursor")
        first = self.items[0]["sequence"] if self.items else self.sequence + 1
        return {
            "latest_sequence": self.sequence,
            "lost_receipts": max(0, first - cursor - 1),
            "receipts": deepcopy([item for item in self.items if item["sequence"] > cursor]),
            "timing_source": "host private IPC receipt; firmware sampling/exposure unqualified",
        }
