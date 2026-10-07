"""Bounded original socket reads, before decoding or line normalization.

The window covers recv calls observed while a command is pending. It may
include status, realtime replies, pre-existing partial lines and trailing bytes
coalesced with the acknowledgement. It is not a firmware-authenticated or
exclusively command-attributed transcript. File transfer is outside this scope.
"""

from __future__ import annotations

import base64
import hashlib

MAX_RECEIVE_WINDOW = 65536


class ReceiveWindow:
    def __init__(self) -> None:
        self.count = 0
        self.digest = hashlib.sha256()
        self.original: bytearray | None = bytearray()

    def append(self, data: bytes) -> None:
        self.count += len(data)
        self.digest.update(data)
        if self.original is not None:
            if self.count > MAX_RECEIVE_WINDOW:
                self.original = None
            else:
                self.original.extend(data)

    def evidence(self, connection_id: str | None, command_payload: bytes, sendall_completed: bool) -> dict:
        return {
            "version": "carvera.controller_receive_window.v1",
            "connection_id": connection_id,
            "scope": "pending_command_socket_recv_calls",
            "original_bytes_base64": base64.b64encode(self.original).decode("ascii")
            if self.original is not None
            else None,
            "sha256": self.digest.hexdigest(),
            "byte_count": self.count,
            "budget_bytes": MAX_RECEIVE_WINDOW,
            "original_bytes_retained": self.original is not None,
            "planned_command_bytes_base64": base64.b64encode(command_payload).decode("ascii"),
            "sendall_completed": sendall_completed,
            "delivery_verified": False,
            "may_include_interleaved_or_unattributed_bytes": True,
            "complete_controller_response_verified": False,
            "firmware_identity_verified": False,
            "measurement_interpretation_available": False,
            "physical_accuracy_verified": False,
            "execution_authorized": False,
        }
