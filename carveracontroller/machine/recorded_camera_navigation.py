"""Navigate only retained same-session status/camera receipt associations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, TypedDict


class RecordedEvent(TypedDict):
    kind: str
    monotonic_at: float


class StatusSession(TypedDict):
    session_id: str
    events: list[RecordedEvent]


class StatusReceiptReader(Protocol):
    @property
    def payload(self) -> StatusSession: ...


class CameraReceiptReader(Protocol):
    @property
    def header(self) -> Mapping[str, object]: ...

    def at(self, timestamp: float) -> Mapping[str, object]: ...


def camera_observation_index(
    replay: StatusReceiptReader, camera: CameraReceiptReader, *, last: bool = False
) -> int | None:
    """Return the first/last status index with a valid camera receipt, or None.

    This reads in-memory metadata only. CameraRunReplay.at enforces its bounds,
    receipt-age limit and source/retention gaps. No interpolation, image reads,
    execution association or CNC commands are introduced.
    """
    if camera.header["recording_session_id"] != replay.payload["session_id"]:
        raise ValueError("Camera part belongs to another status session")
    events = replay.payload["events"]
    indices = range(len(events) - 1, -1, -1) if last else range(len(events))
    for index in indices:
        event = events[index]
        if event["kind"] == "status" and camera.at(event["monotonic_at"])["frame"] is not None:
            return index
    return None
