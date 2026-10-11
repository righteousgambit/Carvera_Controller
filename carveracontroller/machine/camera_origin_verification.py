"""Bounded read-only protocol evidence, separate from sensor qualification."""

from __future__ import annotations

import datetime as dt
import hashlib
import time
from collections.abc import Callable

from carveracontroller.machine.camera_clock import CameraClockExchange
from carveracontroller.machine.webcam import CameraFrame, fetch_frame, validate_camera_url


def verify_origin(
    url: str,
    count: int = 3,
    interval: float = 0.2,
    fetch: Callable[[str, int], CameraFrame] = fetch_frame,
    pause: Callable[[float], None] = time.sleep,
) -> dict[str, object]:
    url = validate_camera_url(url)
    if type(count) is not int or not 2 <= count <= 8 or not 0.1 <= interval <= 0.5:
        raise ValueError("Origin verification requires 2–8 requests spaced 0.1–0.5 seconds apart")
    source = hashlib.sha256(url.encode()).hexdigest()
    samples: list[dict[str, object]] = []
    clocks: list[CameraClockExchange] = []
    captures: list[float | None] = []
    receipts: list[float] = []
    gap = ""
    for sequence in range(1, count + 1):
        try:
            frame = fetch(url, sequence)
        except Exception:
            gap = "Snapshot request or decode failed; request details withheld"
            break
        captures.append(frame.captured_at)
        receipts.append(frame.received_at)
        if frame.clock is not None:
            clocks.append(frame.clock)
        sample: dict[str, object] = {
            "sequence": frame.sequence,
            "jpeg_sha256": hashlib.sha256(frame.jpeg).hexdigest(),
            "dimensions": list(frame.size),
            "reported_frame_utc": frame.captured_at,
            "received_monotonic": frame.received_at,
            "clock": frame.clock.to_dict() if frame.clock is not None else None,
        }
        samples.append(sample)
        age = frame.age()
        sample["reported_age_upper_bound_seconds"] = age
        if frame.clock is None:
            gap = "Origin supplied no accepted request-bound clock evidence"
        elif frame.clock.source_sha256 != source:
            gap = "Clock evidence belongs to another snapshot source"
        elif frame.clock.frame_time_basis != "jpeg-assembled":
            gap = "Origin did not declare the reviewed JPEG-assembly timestamp basis"
        elif age is None or age > 2:
            gap = "Reported frame-time freshness is unavailable or exceeds two seconds"
        del frame  # Retain metadata only, never a multi-image RGB cache.
        if gap:
            break
        if sequence != count:
            pause(interval)
    if not gap:
        if len({clock.server_clock_sha256 for clock in clocks}) != 1:
            gap = "Service clock epoch changed during verification"
        elif len({clock.request_id for clock in clocks}) != count:
            gap = "Timing request identities repeated during verification"
        elif len(set(captures)) < 2:
            gap = "Frame timestamps did not advance during verification"
        elif any(b <= a for a, b in zip(receipts, receipts[1:])):
            gap = "Local frame receipts did not advance during verification"
        elif any(b < a for a, b in zip(captures, captures[1:]) if a is not None and b is not None):
            gap = "Reported frame timestamps moved backwards during verification"
    return {
        "schema": 1,
        "observed_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source_sha256": source,
        "requested_samples": count,
        "protocol_qualified": not gap,
        "gap": gap,
        "samples": samples,
        "evidence_class": "Read-only live snapshot protocol and timestamp progression",
        "assumptions": "Declared precision, no undetected clock steps and 100 ppm relative-rate bound",
        "physical_exposure_qualified": False,
        "service_file_identity_qualified": False,
        "mutation": "JPEG GETs only; no camera or CNC controls, service/configuration changes",
    }
