"""Portable historical ATC configuration receipts; never restore live evidence."""

import hashlib
import json
from datetime import datetime
from pathlib import Path

from .capabilities import parse_slot_readback

MAX_BYTES = 256 * 1024


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def validate_payload(payload):
    fields = {
        "schema",
        "kind",
        "coordinate_frame",
        "contents",
        "completed_at",
        "source",
        "generation",
        "response",
        "response_sha256",
        "slots",
    }
    if not isinstance(payload, dict) or set(payload) != fields:
        raise ValueError("Invalid ATC receipt fields")
    if (
        type(payload["schema"]) is not int
        or payload["schema"] != 1
        or payload["kind"] != "controller_configuration_readback"
        or payload["coordinate_frame"] != "G53_axis_reference"
        or payload["contents"] != "unknown"
    ):
        raise ValueError("Unsupported ATC receipt semantics")
    if type(payload["generation"]) is not int or payload["generation"] < 0:
        raise ValueError("Invalid connection generation")
    try:
        stamp = datetime.fromisoformat(payload["completed_at"])
    except (TypeError, ValueError):
        raise ValueError("Invalid host completion timestamp") from None
    if stamp.tzinfo is None or stamp.utcoffset().total_seconds() != 0:
        raise ValueError("Host completion timestamp must be UTC")
    source = payload["source"]
    if (
        not isinstance(source, dict)
        or set(source) - {"model", "firmware", "protocol", "address"}
        or any(not isinstance(v, str) or len(v) > 256 for v in source.values())
    ):
        raise ValueError("Invalid receipt source metadata")
    response = payload["response"]
    if not isinstance(response, str) or len(response) > 66000:
        raise ValueError("Invalid or oversized normalized response")
    lines = response.splitlines()
    if (
        not lines
        or lines[0] != "Tool Slots Configuration:"
        or len(lines) > 257
        or any(len(line) > 256 or not line.startswith("Tool ") for line in lines[1:])
    ):
        raise ValueError("Invalid normalized response boundary")
    if hashlib.sha256(response.encode()).hexdigest() != payload["response_sha256"]:
        raise ValueError("ATC response digest mismatch")
    slots = [{"number": slot.number, "position_mm": list(slot.position)} for slot in parse_slot_readback(response)]
    if canonical(slots) != canonical(payload["slots"]):
        raise ValueError("ATC slot fields disagree with normalized response")
    return payload


def bundle(receipt):
    payload = validate_payload(
        {
            "schema": 1,
            "kind": "controller_configuration_readback",
            "coordinate_frame": "G53_axis_reference",
            "contents": "unknown",
            "completed_at": receipt.completed_at,
            "source": dict(receipt.source),
            "generation": receipt.generation,
            "response": receipt.response,
            "response_sha256": receipt.response_sha256,
            "slots": [{"number": slot.number, "position_mm": list(slot.position)} for slot in receipt.slots],
        }
    )
    return {"payload": payload, "payload_sha256": digest(payload)}


def decode(raw):
    if len(raw) > MAX_BYTES:
        raise ValueError("ATC receipt exceeds size limit")
    try:
        value = json.loads(raw, object_pairs_hook=unique_fields)
    except (ValueError, UnicodeError):
        raise ValueError("Invalid ATC receipt JSON") from None
    if not isinstance(value, dict) or set(value) != {"payload", "payload_sha256"}:
        raise ValueError("Invalid ATC receipt envelope")
    payload = validate_payload(value["payload"])
    if digest(payload) != value["payload_sha256"]:
        raise ValueError("ATC receipt digest mismatch")
    return value


def unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate receipt field")
        result[key] = value
    return result


def read_file(path):
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    return decode(raw), hashlib.sha256(raw).hexdigest()


def export_file(receipt, path):
    encoded = canonical(bundle(receipt)) + b"\n"
    if len(encoded) > MAX_BYTES:
        raise ValueError("ATC receipt exceeds size limit")
    path = Path(path)
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
    restored, file_hash = read_file(path)
    if restored != bundle(receipt) or file_hash != hashlib.sha256(encoded).hexdigest():
        raise ValueError("ATC export readback mismatch")
    return {"path": str(path), "sha256": file_hash, "pockets": len(receipt.slots)}
