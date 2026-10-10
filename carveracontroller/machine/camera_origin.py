"""Standalone origin timing for the existing JPEG service; no camera controls."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4


@dataclass(frozen=True)
class OriginStamp:
    utc: float
    monotonic: float
    precision: float
    epoch: str


@dataclass(frozen=True)
class OriginRequest:
    nonce: str
    received: OriginStamp


class CameraOriginClock:
    """Sample the service clock and withhold estimates across observed steps.

    Samples bracket a wall-clock read with monotonic reads. Precision covers
    that bracket and timestamp quantization, not UTC accuracy or sensor exposure.
    The 100 ppm rate allowance is an assumption shared with the client.
    """

    def __init__(
        self,
        wall: Callable[[], float] = time.time,
        monotonic: Callable[[], float] = time.monotonic,
        resolution: float | None = None,
    ) -> None:
        self.wall, self.monotonic = wall, monotonic
        self.resolution = time.get_clock_info("time").resolution if resolution is None else resolution
        if (
            type(self.resolution) not in (int, float)
            or not math.isfinite(self.resolution)
            or not 0 < self.resolution <= 1
        ):
            raise ValueError("Unsupported origin clock resolution")
        self._lock = threading.Lock()
        self._epoch = str(uuid4())
        self._previous: OriginStamp | None = None

    def sample(self) -> OriginStamp | None:
        with self._lock:
            try:
                before, utc, after = self.monotonic(), self.wall(), self.monotonic()
                if (
                    not all(
                        type(v) in (int, float) and math.isfinite(v) and v >= 0 and math.ulp(v) <= 1
                        for v in (before, utc, after)
                    )
                    or not 0 <= after - before <= 1
                ):
                    raise ValueError("Unusable origin clock sample")
                midpoint = before + (after - before) / 2
                precision = (
                    max(self.resolution, 1e-6) + (after - before) / 2 + sum(math.ulp(v) for v in (before, utc, after))
                )
                if precision > 1:
                    raise ValueError("Origin clock precision unavailable")
            except (ValueError, TypeError, OverflowError, OSError):
                self._epoch, self._previous = str(uuid4()), None
                return None
            previous = self._previous
            if previous is not None:
                elapsed = midpoint - previous.monotonic
                departure = abs(utc - previous.utc - elapsed)
                tolerance = 0.01 + precision + previous.precision + max(0, elapsed) * 100e-6
                if elapsed < 0 or departure > tolerance:
                    self._epoch = str(uuid4())
            stamp = OriginStamp(utc, midpoint, precision, self._epoch)
            self._previous = stamp
            return stamp

    def begin(self, nonce: str | None) -> OriginRequest | None:
        if not isinstance(nonce, str) or len(nonce) != 32:
            return None
        try:
            if UUID(nonce).hex != nonce:
                return None
        except ValueError:
            return None
        received = self.sample()
        return OriginRequest(nonce, received) if received is not None else None

    def headers(self, request: OriginRequest | None, frame: OriginStamp | None) -> dict[str, str]:
        if request is None:
            return {}
        sent = self.sample()
        if sent is None or request.received.epoch != sent.epoch or sent.utc < request.received.utc:
            return {}
        headers = {
            "X-Camera-Request-ID": request.nonce,
            "X-Camera-Clock-ID": sent.epoch,
            "X-Camera-Request-Received": repr(request.received.utc),
            "X-Camera-Response-Sent": repr(sent.utc),
            "X-Camera-Clock-Precision": repr(max(request.received.precision, sent.precision)),
            "X-Camera-Frame-Time-Basis": "jpeg-assembled",
        }
        if frame is not None and frame.epoch == sent.epoch:
            headers["X-Camera-Frame-Precision"] = repr(frame.precision)
        return headers
