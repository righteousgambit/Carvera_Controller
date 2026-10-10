"""Local probe presets, expiring reviews and durable non-replaying receipt files.

Presets declare two SD values. Neither a non-default diameter nor matching SD
readback establishes calibration, active ATC TLO, or persistence after restart.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

KEYS = ("zprobe.probe_tip_diameter", "zprobe.three_axis_probe_tlo_correction")
APPLICATION_VERSION = "carvera.probe_settings_application.v1"
MAX_BYTES = 4 * 1024 * 1024
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\Z")
IDENTITY = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
KINDS = ("mechanical", "inductive", "oem_wireless")


def canonical(value: object) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(text.encode()) > MAX_BYTES:
        raise ValueError("Probe record is too large")
    return text


def fingerprint(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json(raw: bytes) -> Any:
    if len(raw) > MAX_BYTES:
        raise ValueError("Probe file is too large")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate probe record key")
            result[key] = value
        return result

    def constant(_value: str) -> None:
        raise ValueError("Nonfinite probe record")

    def number(token: str) -> float:
        value = float(token)
        if not math.isfinite(value):
            raise ValueError("Nonfinite probe record")
        return value

    def integer(token: str) -> int:
        if len(token) > 128:
            raise ValueError("Oversized probe integer")
        return int(token)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant, parse_float=number, parse_int=integer)


def decimal_token(value: object, key: str) -> str:
    if not isinstance(value, str) or not 0 < len(value) < 20 or NUMBER.fullmatch(value) is None:
        raise ValueError("Setting needs a decimal token of at most 19 characters")
    number = float(value)
    if not math.isfinite(number) or abs(number) > 500 or key == KEYS[0] and number <= 0:
        raise ValueError("Tip diameter must be positive; both settings are bounded to 500 mm")
    return value


def dimension_token(value: float, key: str) -> str:
    return decimal_token(format(value, ".12g"), key)


def text(value: object, required: bool = False, maximum: int = 128) -> str:
    if not isinstance(value, str) or len(value) > maximum or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid probe preset text")
    value = value.strip()
    if required and not value:
        raise ValueError("Name the probe preset")
    return value


def preset(value: object) -> dict[str, str]:
    fields = {"name", "kind", "tip_diameter_token", "tlo_correction_token", "note"}
    if not isinstance(value, dict) or set(value) != fields or value["kind"] not in KINDS:
        raise ValueError("Invalid probe preset")
    return {
        "name": text(value["name"], True),
        "kind": value["kind"],
        "tip_diameter_token": decimal_token(value["tip_diameter_token"], KEYS[0]),
        "tlo_correction_token": decimal_token(value["tlo_correction_token"], KEYS[1]),
        "note": text(value["note"], maximum=512),
    }


def library(value: object) -> list[dict[str, str]]:
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "presets"}
        or type(value["schema"]) is not int
        or value["schema"] != 1
    ):
        raise ValueError("Unknown probe preset file")
    entries = value["presets"]
    if not isinstance(entries, list) or len(entries) > 256:
        raise ValueError("At most 256 probe presets are supported")
    result = [preset(p) for p in entries]
    if len({p["name"] for p in result}) != len(result):
        raise ValueError("Duplicate probe preset name")
    return sorted(result, key=lambda p: p["name"].casefold())


def directory_sync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class PresetStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> list[dict[str, str]]:
        try:
            with self.path.open("rb") as stream:
                return library(strict_json(stream.read(MAX_BYTES + 1)))
        except FileNotFoundError:
            return []

    def save(self, value: object) -> list[dict[str, str]]:
        item = preset(value)
        entries = {p["name"]: p for p in self.load()}
        entries[item["name"]] = item
        return self.replace({"schema": 1, "presets": list(entries.values())})

    def replace(self, value: object) -> list[dict[str, str]]:
        # Preserve malformed existing files, including on explicit import.
        self.load()
        entries = library(value)
        raw = canonical({"schema": 1, "presets": entries}).encode() + b"\n"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=self.path.parent, prefix=".probe-presets-", delete=False) as stream:
            staged = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            staged.replace(self.path)
            directory_sync(self.path.parent)
            if self.load() != entries:
                raise ValueError("Probe preset readback differs")
        finally:
            if staged.exists():
                staged.unlink()
        return entries


def expected_settings(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != set(KEYS):
        raise ValueError("Both original settings are required")
    for key in KEYS:
        item = value[key]
        if not isinstance(item, dict) or set(item) != {"state", "value_mm", "original_numeric_token"}:
            raise ValueError("Original setting fields differ")
        if item["state"] == "missing":
            if item["value_mm"] is not None or item["original_numeric_token"] is not None:
                raise ValueError("Missing setting must remain explicitly absent")
        elif item["state"] == "reported":
            token = decimal_token(item["original_numeric_token"], key)
            if type(item["value_mm"]) not in (int, float) or item["value_mm"] != float(token):
                raise ValueError("Original setting value differs from its token")
        else:
            raise ValueError("Unknown original setting state")
    return copy.deepcopy(value)


@dataclass(frozen=True)
class ProbeReview:
    session_id: str
    connection_id: str
    context_sha256: str
    created_at: float
    params_json: str
    preset_json: str

    @classmethod
    def create(
        cls, session: str, connection: str, context: object, original: object, proposed: object, now: float
    ) -> ProbeReview:
        if (
            not isinstance(session, str)
            or not isinstance(connection, str)
            or not IDENTITY.fullmatch(session)
            or not IDENTITY.fullmatch(connection)
        ):
            raise ValueError("Review needs an exact backend lease")
        item, before = preset(proposed), expected_settings(original)
        settings = dict(zip(KEYS, (item["tip_diameter_token"], item["tlo_correction_token"])))
        if all(
            before[key]["state"] == "reported" and before[key]["original_numeric_token"] == settings[key]
            for key in KEYS
        ):
            raise ValueError("Both requested tokens already match; no application is needed")
        if type(now) not in (int, float) or not math.isfinite(now) or now < 0:
            raise ValueError("Review clock unavailable")
        return cls(
            session,
            connection,
            fingerprint(context),
            now,
            canonical(
                {
                    "schema_version": APPLICATION_VERSION,
                    "connection_id": connection,
                    "expected_settings": before,
                    "settings": settings,
                }
            ),
            canonical(item),
        )

    @property
    def params(self) -> dict[str, Any]:
        return cast(dict[str, Any], json.loads(self.params_json))

    def authorize(self, session: str, connection: str, context: object, now: float) -> dict[str, Any]:
        if (session, connection, fingerprint(context)) != (self.session_id, self.connection_id, self.context_sha256):
            raise ValueError("Machine, connection or preset changed; read and review again")
        if type(now) not in (int, float) or not math.isfinite(now) or not 0 <= now - self.created_at <= 30:
            raise ValueError("Probe settings review expired; review again")
        return self.params


def load_journal(path: Path) -> list[dict[str, Any]]:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES or not raw.endswith(b"\n"):
        raise ValueError("Incomplete or oversized probe receipt file; retain it for review")
    result: list[dict[str, Any]] = []
    previous = None
    for line in raw.splitlines():
        row = strict_json(line)
        if not isinstance(row, dict) or set(row) != {"schema", "sequence", "previous_sha256", "record", "sha256"}:
            raise ValueError("Unknown probe receipt row")
        body = {k: v for k, v in row.items() if k != "sha256"}
        if (
            row["schema"] != "carvera.probe_journal.v1"
            or type(row["sequence"]) is not int
            or row["sequence"] != len(result) + 1
            or row["previous_sha256"] != previous
            or row["sha256"] != fingerprint(body)
            or not isinstance(row["record"], dict)
        ):
            raise ValueError("Probe receipt chain differs; retain it for review")
        result.append(row)
        previous = row["sha256"]
    if not result:
        raise ValueError("Empty probe receipt file")
    return result


def append_journal(path: Path, record: dict[str, Any], *, new: bool = False) -> None:
    rows = [] if new else load_journal(path)
    body = {
        "schema": "carvera.probe_journal.v1",
        "sequence": len(rows) + 1,
        "previous_sha256": rows[-1]["sha256"] if rows else None,
        "record": record,
    }
    raw = canonical({**body, "sha256": fingerprint(body)}).encode() + b"\n"
    if not new and path.stat().st_size + len(raw) > MAX_BYTES:
        raise ValueError("Probe receipt budget exhausted")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb" if new else "ab") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    if new:
        directory_sync(path.parent)
    if load_journal(path)[-1]["record"] != record:
        raise ValueError("Probe receipt readback differs")
