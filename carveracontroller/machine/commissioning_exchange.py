"""Portable before/after historical review, with source capture and recomputation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from carveracontroller.machine.commissioning_capture import CommissioningCapture, decode_capture
from carveracontroller.machine.slot_exchange import canonical, digest

MAX_BYTES = 64 * 1024**2
HAL_GROUPS = ("HAL pins", "HAL signals", "HAL parameters")


@dataclass(frozen=True)
class ComparisonReview:
    capture: CommissioningCapture
    raw_capture: bytes
    reference: int
    selected: int
    group: str
    saved_at: str
    file_sha256: str


def decode_comparison(raw: bytes, source: str) -> ComparisonReview:
    if len(raw) > MAX_BYTES:
        raise ValueError("Comparison exceeds 64 MiB")
    try:
        record = json.loads(raw)
        if not isinstance(record, dict) or set(record) != {"payload", "payload_sha256"}:
            raise ValueError("Invalid comparison envelope")
        payload = record["payload"]
        if not isinstance(payload, dict) or set(payload) != {
            "schema",
            "kind",
            "execution_available",
            "saved_at",
            "capture_sha256",
            "capture",
            "reference",
            "selected",
            "group",
        }:
            raise ValueError("Invalid comparison fields")
        if record["payload_sha256"] != digest(payload):
            raise ValueError("Comparison payload digest mismatch")
        if (
            type(payload["schema"]) is not int
            or payload["schema"] != 1
            or payload["kind"] != "historical_commissioning_comparison"
            or payload["execution_available"] is not False
        ):
            raise ValueError("Unsupported comparison semantics")
        if not isinstance(payload["saved_at"], str) or len(payload["saved_at"]) > 128:
            raise ValueError("Bounded comparison UTC timestamp required")
        stamp = datetime.fromisoformat(payload["saved_at"])
        offset = stamp.utcoffset()
        if offset is None or offset.total_seconds() != 0:
            raise ValueError("Comparison timestamp must be UTC")
        capture_raw = payload["capture"].encode("utf-8")
        capture = decode_capture(capture_raw, source)
        if payload["capture_sha256"] != capture.sha256:
            raise ValueError("Embedded capture hash mismatch")
        for field in ("reference", "selected"):
            index = payload[field]
            if type(index) is not int or not 0 <= index < len(capture.observations):
                raise ValueError("Comparison sample index outside capture")
        if payload["group"] not in HAL_GROUPS:
            raise ValueError("Comparison HAL group required")
        return ComparisonReview(
            capture,
            capture_raw,
            payload["reference"],
            payload["selected"],
            payload["group"],
            payload["saved_at"],
            hashlib.sha256(raw).hexdigest(),
        )
    except (KeyError, TypeError, AttributeError, UnicodeError, OverflowError, RecursionError) as exc:
        raise ValueError("Malformed historical comparison") from exc


def read_comparison(path: str | Path) -> ComparisonReview:
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    return decode_comparison(raw, str(path))


def write_comparison(
    capture: CommissioningCapture,
    reference: int,
    selected: int,
    group: str,
    path: str | Path,
    raw_capture: bytes | None = None,
) -> ComparisonReview:
    if raw_capture is None:
        with Path(capture.source).open("rb") as stream:
            raw_capture = stream.read(20 * 1024**2 + 1)
    if hashlib.sha256(raw_capture).hexdigest() != capture.sha256:
        raise ValueError("Original capture changed since import; re-import before exporting")
    payload = {
        "schema": 1,
        "kind": "historical_commissioning_comparison",
        "execution_available": False,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "capture_sha256": capture.sha256,
        "capture": raw_capture.decode("utf-8"),
        "reference": reference,
        "selected": selected,
        "group": group,
    }
    raw = canonical({"payload": payload, "payload_sha256": digest(payload)})
    decode_comparison(raw, str(path))
    # Exclusive creation preserves any previous receipt and failed evidence.
    with Path(path).open("xb") as stream:
        stream.write(raw)
    result = read_comparison(path)
    if result.file_sha256 != hashlib.sha256(raw).hexdigest():
        raise ValueError("Comparison readback differs; written evidence retained")
    return result
