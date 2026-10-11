"""Navigate only retained same-session status/camera receipt associations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from carveracontroller.machine.run_recording import RecordingPayload


class StatusReceiptReader(Protocol):
    @property
    def payload(self) -> RecordingPayload: ...


class CameraReceiptReader(Protocol):
    @property
    def header(self) -> Mapping[str, object]: ...

    def at(self, timestamp: float, /) -> Mapping[str, object]: ...


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


def adjacent_camera_observation_index(
    replay: StatusReceiptReader,
    camera: CameraReceiptReader,
    current: int,
    *,
    previous: bool = False,
) -> int | None:
    """Find an adjacent status associated with a different retained image.

    Several status packets can refer to one camera receipt. Skip those repeated
    associations, gaps and non-status events, without wrapping at either end.
    Only retained metadata is read; this does not infer exposure/motion timing.
    """
    if camera.header["recording_session_id"] != replay.payload["session_id"]:
        raise ValueError("Camera part belongs to another status session")
    events = replay.payload["events"]
    if type(current) is not int or not 0 <= current < len(events):
        raise ValueError("Current status observation is outside the recording")

    def identity(index: int) -> tuple[object, object] | None:
        event = events[index]
        if event["kind"] != "status":
            return None
        frame = camera.at(event["monotonic_at"])["frame"]
        if not isinstance(frame, Mapping):
            return None
        return frame["generation"], frame["attempt"]

    selected = identity(current)
    indices = range(current - 1, -1, -1) if previous else range(current + 1, len(events))
    for index in indices:
        candidate = identity(index)
        if candidate is not None and candidate != selected:
            return index
    return None
