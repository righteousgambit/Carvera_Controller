"""Request-bound camera clock evidence; sensor exposure remains unqualified."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from uuid import UUID

RATE_BOUND_PPM = 100.0  # Declared relative-rate assumption, not measured oscillator accuracy.
MAX_FRAME_EXTRAPOLATION = 30.0


def _number(value: object) -> float:
    if type(value) not in (float, int) or not isinstance(value, (int, float)):
        raise ValueError("Camera clock evidence requires numeric timestamps")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError("Camera clock timestamp exceeds finite range") from exc
    if not math.isfinite(number) or number < 0:
        raise ValueError("Camera clock evidence requires finite nonnegative timestamps")
    return number


def _hash(value: object) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Invalid camera clock fingerprint")
    return value


@dataclass(frozen=True)
class CameraClockExchange:
    request_id: str
    source_sha256: str
    server_clock_sha256: str
    sent_monotonic: float
    received_monotonic: float
    sent_utc: float
    received_utc: float
    server_received_utc: float
    server_sent_utc: float
    precision_seconds: float
    frame_precision_seconds: float | None = None
    frame_time_basis: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, str) or UUID(self.request_id).hex != self.request_id:
            raise ValueError("Invalid camera timing request identity")
        _hash(self.source_sha256)
        _hash(self.server_clock_sha256)
        for value in (
            self.sent_monotonic,
            self.received_monotonic,
            self.sent_utc,
            self.received_utc,
            self.server_received_utc,
            self.server_sent_utc,
            self.precision_seconds,
        ):
            _number(value)
        if self.frame_time_basis not in (None, "jpeg-assembled", "sensor-exposure"):
            raise ValueError("Unsupported camera frame timestamp basis")
        if self.frame_precision_seconds is not None and _number(self.frame_precision_seconds) > 1:
            raise ValueError("Camera frame timestamp precision exceeds its bounds")
        if (
            max(
                math.ulp(v)
                for v in (
                    self.sent_monotonic,
                    self.received_monotonic,
                    self.sent_utc,
                    self.received_utc,
                    self.server_received_utc,
                    self.server_sent_utc,
                )
            )
            > 1
        ):
            raise ValueError("Camera timestamps exceed the supported numeric resolution")
        elapsed = self.received_monotonic - self.sent_monotonic
        if not 0 <= elapsed <= 5 or not 0 <= self.precision_seconds <= 1:
            raise ValueError("Camera timing exchange exceeds its bounds")
        if abs(self.received_utc - self.sent_utc - elapsed) > 0.01:
            raise ValueError("Local wall clock changed during camera request")
        if self.server_sent_utc < self.server_received_utc:
            raise ValueError("Camera server clock moved backwards during request")
        low, high = self.offset_bounds
        if low > high:
            raise ValueError("Camera server timestamps are inconsistent with the request interval")

    @property
    def uncertainty_seconds(self) -> float:
        # Nonnegative one-way transit implies t3-t4 <= server-client <= t2-t1.
        # Include declared server quantization and the observed local wall/mono
        # discrepancy. No symmetric-link or HTTP Date assumption is made.
        discrepancy = abs(self.received_utc - self.sent_utc - (self.received_monotonic - self.sent_monotonic))
        margin = (
            sum(
                math.ulp(v)
                for v in (
                    self.sent_monotonic,
                    self.received_monotonic,
                    self.sent_utc,
                    self.received_utc,
                    self.server_received_utc,
                    self.server_sent_utc,
                )
            )
            + self.precision_seconds
            + discrepancy
            + 1e-6
            + (self.received_monotonic - self.sent_monotonic) * RATE_BOUND_PPM * 1e-6
        )
        return margin

    @property
    def offset_bounds(self) -> tuple[float, float]:
        margin = self.uncertainty_seconds
        return self.server_sent_utc - self.received_utc - margin, self.server_received_utc - self.sent_utc + margin

    def frame_bounds(self, server_frame_utc: float) -> tuple[float, float]:
        if self.frame_precision_seconds is None:
            raise ValueError("Server frame timestamp precision is unavailable")
        stamp = _number(server_frame_utc)
        distance = self.server_sent_utc - stamp
        if not -(self.precision_seconds + self.frame_precision_seconds) <= distance <= MAX_FRAME_EXTRAPOLATION:
            raise ValueError("Server frame time lies outside the bounded timing horizon")
        margin = self.uncertainty_seconds
        rate_margin = abs(distance) * RATE_BOUND_PPM * 1e-6 + self.frame_precision_seconds + math.ulp(stamp)
        return (
            self.sent_monotonic + (stamp - self.server_received_utc) - margin - rate_margin,
            self.received_monotonic + (stamp - self.server_sent_utc) + margin + rate_margin,
        )

    def to_dict(self) -> dict[str, object]:
        return {"schema": 1, **asdict(self)}

    @classmethod
    def from_dict(cls, value: object) -> CameraClockExchange:
        fields = {"schema", *cls.__dataclass_fields__}
        if not isinstance(value, dict) or set(value) not in (fields, fields - {"frame_time_basis"}):
            raise ValueError("Invalid camera clock evidence record")
        if type(value["schema"]) is not int or value["schema"] != 1:
            raise ValueError("Unsupported camera clock evidence schema")
        identity = value["request_id"]
        if not isinstance(identity, str):
            raise ValueError("Invalid camera timing request identity")
        sent_mono, received_mono, sent_utc, received_utc, server_received, server_sent, precision = (
            _number(value[name])
            for name in (
                "sent_monotonic",
                "received_monotonic",
                "sent_utc",
                "received_utc",
                "server_received_utc",
                "server_sent_utc",
                "precision_seconds",
            )
        )
        return cls(
            identity,
            _hash(value["source_sha256"]),
            _hash(value["server_clock_sha256"]),
            sent_mono,
            received_mono,
            sent_utc,
            received_utc,
            server_received,
            server_sent,
            precision,
            _number(value["frame_precision_seconds"]) if value["frame_precision_seconds"] is not None else None,
            _frame_basis(value.get("frame_time_basis")),
        )


def camera_clock_headers(
    request_id: str,
    received_utc: float,
    clock_id: str,
    sent_utc: float,
    precision_seconds: float,
    frame_precision_seconds: float | None = None,
) -> dict[str, str]:
    """Origin-service hook: call at request arrival and immediately before headers.

    clock_id is a service-start UUID. This hook changes no clock or camera; the
    service must retain its own sensor/frame timestamp and avoid cached echoes.
    """
    request = UUID(request_id).hex
    clock = str(UUID(clock_id))
    received, sent = _number(received_utc), _number(sent_utc)
    precision = _number(precision_seconds)
    if precision > 1:
        raise ValueError("Camera timestamp precision exceeds its bounds")
    if sent < received:
        raise ValueError("Camera server clock moved backwards during request")
    headers = {
        "X-Camera-Request-ID": request,
        "X-Camera-Clock-ID": clock,
        "X-Camera-Request-Received": repr(received),
        "X-Camera-Response-Sent": repr(sent),
        "X-Camera-Clock-Precision": repr(precision),
    }
    if frame_precision_seconds is not None:
        frame_precision = _number(frame_precision_seconds)
        if frame_precision > 1:
            raise ValueError("Camera frame timestamp precision exceeds its bounds")
        headers["X-Camera-Frame-Precision"] = repr(frame_precision)
    return headers


def read_camera_clock(
    headers: Mapping[str, str],
    request_id: str,
    source_sha256: str,
    sent_monotonic: float,
    received_monotonic: float,
    sent_utc: float,
    received_utc: float,
) -> CameraClockExchange:
    if headers.get("X-Camera-Request-ID") != request_id:
        raise ValueError("Camera service did not echo the current timing request")
    clock = str(UUID(headers["X-Camera-Clock-ID"]))
    return CameraClockExchange(
        request_id,
        source_sha256,
        hashlib.sha256(clock.encode()).hexdigest(),
        sent_monotonic,
        received_monotonic,
        sent_utc,
        received_utc,
        float(headers["X-Camera-Request-Received"]),
        float(headers["X-Camera-Response-Sent"]),
        float(headers["X-Camera-Clock-Precision"]),
        float(headers["X-Camera-Frame-Precision"]) if headers.get("X-Camera-Frame-Precision") else None,
        _frame_basis(headers.get("X-Camera-Frame-Time-Basis") or None),
    )


def _frame_basis(value: object) -> str | None:
    if value is None or isinstance(value, str) and value in ("jpeg-assembled", "sensor-exposure"):
        return value
    raise ValueError("Unsupported camera frame timestamp basis")


def camera_timing_notice(exchange: CameraClockExchange | None, captured_at: float | None) -> str:
    if exchange is None:
        return "Clock exchange unavailable · receipt-time association only · exposure synchronization unqualified"
    low, high = exchange.offset_bounds
    text = f"Reported server−desktop clock interval {low:+.6f}…{high:+.6f} s"
    if exchange.frame_time_basis == "jpeg-assembled":
        text += "\nFrame timestamp basis: JPEG assembled after FFmpeg delivery"
    elif exchange.frame_time_basis == "sensor-exposure":
        text += "\nFrame timestamp basis: service-declared sensor exposure, unverified"
    else:
        text += "\nFrame timestamp basis unspecified"
    if captured_at is not None:
        try:
            start, end = exchange.frame_bounds(captured_at)
            text += f"\nServer frame-time window {start:.6f}…{end:.6f} local monotonic s"
        except ValueError as exc:
            text += "\n" + str(exc)
    return text + "\nNo clock steps and 100 ppm relative-rate bound assumed; sensor exposure unqualified"
