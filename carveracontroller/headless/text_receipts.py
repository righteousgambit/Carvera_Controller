"""Bounded original IPC receipts for normalized unsolicited controller text.

These retain the private child's bytes, not the original controller socket
bytes. Consumers must not silently promote them to byte-qualified measurements.
"""

from __future__ import annotations

import base64
import hashlib
import math
from collections import deque
from copy import deepcopy
from typing import Any

from ..machine.probe_settings_workflow import strict_json


class TextReceipts:
    def __init__(self, capacity: int = 256) -> None:
        if type(capacity) is not int or not 2 <= capacity <= 4096:
            raise ValueError("Invalid text receipt capacity")
        self.items: deque[dict[str, Any]] = deque(maxlen=capacity)
        self.sequence = 0
        self.connection_id: str | None = None

    def observe(self, event: dict[str, Any], raw: bytes, now: float | None, utc: float) -> None:
        if event.get("event") == "connection":
            identity = event.get("connection_id")
            if (
                type(event.get("connected")) is not bool
                or event["connected"]
                and (not isinstance(identity, str) or not 0 < len(identity) <= 100)
            ):
                raise ValueError("Invalid connection event")
            self.connection_id = identity if event["connected"] else None
            return
        if event.get("event") != "unsolicited_response":
            return
        if now is None:
            raise ValueError("Text receipt clock unavailable")
        text = event.get("text")
        if (
            not isinstance(text, str)
            or len(text) > 512
            or not isinstance(raw, bytes)
            or not 0 < len(raw) <= 65536
            or not raw.endswith(b"\n")
            or strict_json(raw) != event
            or any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in (now, utc))
        ):
            raise ValueError("Invalid original text event")
        self.sequence += 1
        self.items.append(
            {
                "sequence": self.sequence,
                "connection_id": self.connection_id,
                "received_at_s": now,
                "received_utc_s": utc,
                "text": text,
                "original_ipc_bytes_base64": base64.b64encode(raw).decode(),
                "ipc_sha256": hashlib.sha256(raw).hexdigest(),
                "controller_original_bytes_retained": False,
                "normalized_by_backend": True,
                "text_may_be_truncated": len(text) == 512,
                "command_attribution_verified": False,
            }
        )

    def since(self, cursor: int) -> dict[str, Any]:
        if type(cursor) is not int or not 0 <= cursor <= self.sequence:
            raise ValueError("Invalid text receipt cursor")
        first = self.items[0]["sequence"] if self.items else self.sequence + 1
        return {
            "latest_sequence": self.sequence,
            "lost_receipts": max(0, first - cursor - 1),
            "receipts": deepcopy([item for item in self.items if item["sequence"] > cursor]),
            "source": "original private IPC; normalized unsolicited controller text",
            "controller_original_bytes_retained": False,
            "command_attribution_verified": False,
        }
