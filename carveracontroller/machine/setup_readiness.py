"""Setup evidence bound to geometry; no controller commands or run permission.

An operator receipt records a reported measurement, not independent verification.
Changing a dependency or expiration makes a receipt stale without deleting it.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

GROUPS = ("stock", "workholding", "tools", "offsets")


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    title: str
    state: str
    detail: str
    target: str
    receipt: dict | None = None


class SetupEvidenceStore:
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, path=None):
        self.path = Path(path or Path.home() / ".carvera/setup-evidence.json")
        self.error = None
        try:
            self.records = self._read()
        except (ValueError, OSError) as exc:
            self.records, self.error = [], str(exc)

    @staticmethod
    def validate(record):
        keys = {"machine_id", "group", "fingerprint", "source", "method", "measured_at", "expires_at"}
        if not isinstance(record, dict) or set(record) != keys:
            raise ValueError("Invalid setup receipt fields")
        for key in ("machine_id", "source", "method"):
            if not isinstance(record[key], str) or not record[key].strip() or len(record[key]) > 1000:
                raise ValueError(f"Receipt requires {key} (up to 1000 characters)")
        if record["group"] not in GROUPS:
            raise ValueError("Unknown setup evidence group")
        digest = record["fingerprint"]
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid setup fingerprint")
        for key in ("measured_at", "expires_at"):
            if (
                type(record[key]) not in (int, float)
                or not math.isfinite(record[key])
                or not 0 <= record[key] <= 253402300799
            ):
                raise ValueError("Receipt times must be valid finite UTC dates")
        if record["measured_at"] < 0 or record["expires_at"] <= record["measured_at"]:
            raise ValueError("Receipt expiration must follow measurement")
        return dict(record)

    def _read(self):
        if not self.path.exists():
            return []
        if self.path.stat().st_size > self.MAX_BYTES:
            raise ValueError("Setup evidence exceeds 2 MiB")
        document = json.loads(self.path.read_text())
        if not isinstance(document, dict) or set(document) != {"schema_version", "receipts"}:
            raise ValueError("Invalid setup evidence document")
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise ValueError("Unsupported setup evidence schema")
        records = document["receipts"]
        if not isinstance(records, list) or len(records) > 2000:
            raise ValueError("Setup receipt limit is 2000")
        return [self.validate(record) for record in records]

    def record(self, machine_id, group, snapshot, source, method, measured_at, expires_at):
        receipt = self.validate(
            {
                "machine_id": machine_id,
                "group": group,
                "fingerprint": fingerprint(snapshot),
                "source": source,
                "method": method,
                "measured_at": measured_at,
                "expires_at": expires_at,
            }
        )
        if self.error:
            raise ValueError(f"Repair setup evidence before saving: {self.error}")
        records = self._read() + [receipt]
        if len(records) > 2000:
            raise ValueError("Setup receipt limit is 2000; preserve/archive prior evidence before adding more")
        raw = json.dumps({"schema_version": 1, "receipts": records}, indent=2, allow_nan=False)
        if len(raw.encode()) > self.MAX_BYTES:
            raise ValueError("Setup evidence exceeds 2 MiB")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=self.path.parent, delete=False) as stream:
                name = stream.name
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
        self.records = records
        return receipt

    def latest(self, machine_id, group):
        return next((r for r in reversed(self.records) if r["machine_id"] == machine_id and r["group"] == group), None)


def evaluate_setup(machine_id, snapshots, present, store, now):
    """All four groups remain evidence checks, never sufficient run authorization."""
    titles = {
        "stock": "Stock dimensions & placement",
        "workholding": "Fixture & vise mounting",
        "tools": "Physical tooling & lengths",
        "offsets": "Work coordinate alignment",
    }
    targets = {"stock": "Scene", "workholding": "Scene", "tools": "Setup", "offsets": "Overview"}
    items = []
    for group in GROUPS:
        receipt = store.latest(machine_id, group) if machine_id else None
        if not present.get(group):
            state, detail = "unresolved", "Configure this setup component before recording a check."
        elif store.error:
            state, detail = "unresolved", "Evidence store unavailable: " + store.error
        elif receipt is None:
            state, detail = "entered", "Saved/entered setup only; no measurement receipt."
        elif receipt["fingerprint"] != fingerprint(snapshots[group]):
            state, detail = "stale", "Setup dependencies changed after this measurement. Recheck the current setup."
        elif receipt["method"] == "Invalidated after physical change":
            state, detail = "stale", "Physical change: " + receipt["source"] + ". Record a new measurement."
        elif not receipt["measured_at"] <= now < receipt["expires_at"]:
            state, detail = "stale", "Measurement is expired or dated in the future."
        else:
            state, detail = "measured", "Operator recorded · " + receipt["method"] + " · " + receipt["source"]
        items.append(ReadinessItem(group, titles[group], state, detail, targets[group], receipt))
    return tuple(items)
