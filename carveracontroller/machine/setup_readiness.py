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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

GROUPS = ("stock", "workholding", "tools", "offsets")


class MountingDetails(TypedDict):
    hole_labels: list[str]
    jaw_contact_notes: str
    stock_protrusion_mm: float | None


def validate_mounting(value: object) -> MountingDetails:
    if not isinstance(value, dict) or set(value) != {"hole_labels", "jaw_contact_notes", "stock_protrusion_mm"}:
        raise ValueError("Invalid mounting record fields")
    labels, notes, protrusion = value["hole_labels"], value["jaw_contact_notes"], value["stock_protrusion_mm"]
    if not isinstance(labels, list) or len(labels) > 16:
        raise ValueError("Mounting record accepts up to 16 operator hole labels")
    cleaned = []
    for label in labels:
        if not isinstance(label, str) or not label.strip() or len(label) > 80 or any(ord(c) < 32 for c in label):
            raise ValueError("Each hole label requires 1–80 printable characters")
        cleaned.append(label.strip())
    if len({label.casefold() for label in cleaned}) != len(cleaned):
        raise ValueError("Hole labels must be unique")
    if not isinstance(notes, str) or len(notes) > 1000:
        raise ValueError("Jaw contact notes are limited to 1000 characters")
    if protrusion is not None and (
        type(protrusion) not in (int, float) or not 0 <= protrusion <= 1000 or not math.isfinite(protrusion)
    ):
        raise ValueError("Measured stock protrusion must be finite and between 0 and 1000 mm")
    if not cleaned and not notes.strip() and protrusion is None:
        raise ValueError("Enter at least one measured mounting detail")
    return {"hole_labels": cleaned, "jaw_contact_notes": notes.strip(), "stock_protrusion_mm": protrusion}


class _ReceiptRequired(TypedDict):
    machine_id: str
    group: str
    fingerprint: str
    source: str
    method: str
    measured_at: float
    expires_at: float


class SetupReceipt(_ReceiptRequired, total=False):
    mounting: MountingDetails


ReadinessState = Literal["unresolved", "entered", "stale", "measured"]


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(frozen=True)
class ReadinessItem:
    key: str
    title: str
    state: ReadinessState
    detail: str
    target: str
    receipt: SetupReceipt | None = None


class SetupEvidenceStore:
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or Path.home() / ".carvera/setup-evidence.json")
        self.mounting_path = self.path.with_name(self.path.stem + ".mounting.json")
        self.error: str | None = None
        try:
            self.records = self._read()
        except (ValueError, OSError) as exc:
            self.records, self.error = [], str(exc)

    @staticmethod
    def validate(record: object) -> SetupReceipt:
        keys = {"machine_id", "group", "fingerprint", "source", "method", "measured_at", "expires_at"}
        if not isinstance(record, dict) or set(record) not in (keys, keys | {"mounting"}):
            raise ValueError("Invalid setup receipt fields")

        def text(key: str) -> str:
            value = record[key]
            if not isinstance(value, str) or not value.strip() or len(value) > 1000:
                raise ValueError(f"Receipt requires {key} (up to 1000 characters)")
            return value

        machine_id, source, method = text("machine_id"), text("source"), text("method")
        group = text("group")
        if group not in GROUPS:
            raise ValueError("Unknown setup evidence group")
        digest = text("fingerprint")
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid setup fingerprint")
        measured, expires = _utc_time(record["measured_at"]), _utc_time(record["expires_at"])
        if expires <= measured:
            raise ValueError("Receipt expiration must follow measurement")
        result: SetupReceipt = {
            "machine_id": machine_id,
            "group": group,
            "fingerprint": digest,
            "source": source,
            "method": method,
            "measured_at": measured,
            "expires_at": expires,
        }
        if "mounting" in record:
            if group != "workholding":
                raise ValueError("Mounting details belong to a workholding receipt")
            result["mounting"] = validate_mounting(record["mounting"])
        return result

    def _read(self) -> list[SetupReceipt]:
        if not self.path.exists():
            return []
        if self.path.stat().st_size > self.MAX_BYTES:
            raise ValueError("Setup evidence exceeds 2 MiB")
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(document, dict) or set(document) != {"schema_version", "receipts"}:
            raise ValueError("Invalid setup evidence document")
        if type(document["schema_version"]) is not int or document["schema_version"] != 1:
            raise ValueError("Unsupported setup evidence schema")
        records = document["receipts"]
        if not isinstance(records, list) or len(records) > 2000:
            raise ValueError("Setup receipt limit is 2000")
        attachments = self._read_mounting()
        result = []
        for raw in records:
            record = self.validate(raw)
            identity = fingerprint({key: item for key, item in record.items() if key != "mounting"})
            if identity in attachments:
                if record["group"] != "workholding":
                    raise ValueError("Mounting attachment belongs to a non-workholding receipt")
                if "mounting" in record and record["mounting"] != attachments[identity]:
                    raise ValueError("Inline and retained mounting details differ")
                record["mounting"] = attachments[identity]
            result.append(record)
        return result

    def _read_mounting(self) -> dict[str, MountingDetails]:
        if not self.mounting_path.exists():
            return {}
        if self.mounting_path.stat().st_size > self.MAX_BYTES:
            raise ValueError("Mounting attachments exceed 2 MiB")
        document = json.loads(self.mounting_path.read_text(encoding="utf-8"))
        if (
            not isinstance(document, dict)
            or set(document) != {"schema_version", "attachments"}
            or type(document["schema_version"]) is not int
            or document["schema_version"] != 1
            or not isinstance(document["attachments"], dict)
            or len(document["attachments"]) > 2000
        ):
            raise ValueError("Invalid mounting attachment document")
        result = {}
        for identity, details in document["attachments"].items():
            if (
                not isinstance(identity, str)
                or len(identity) != 64
                or any(c not in "0123456789abcdef" for c in identity)
            ):
                raise ValueError("Invalid mounting receipt identity")
            result[identity] = validate_mounting(details)
        return result

    def record(
        self,
        machine_id: str,
        group: str,
        snapshot: object,
        source: str,
        method: str,
        measured_at: object,
        expires_at: object,
        *,
        mounting: object = None,
    ) -> SetupReceipt:
        receipt = self.validate(
            {
                "machine_id": machine_id,
                "group": group,
                "fingerprint": fingerprint(snapshot),
                "source": source,
                "method": method,
                "measured_at": measured_at,
                "expires_at": expires_at,
                **({"mounting": mounting} if mounting is not None else {}),
            }
        )
        if self.error:
            raise ValueError(f"Repair setup evidence before saving: {self.error}")
        records = self._read() + [receipt]
        if len(records) > 2000:
            raise ValueError("Setup receipt limit is 2000; preserve/archive prior evidence before adding more")
        # Preserve orphan attachments from an interrupted earlier base commit.
        attachments = self._read_mounting()
        base_records = []
        for record in records:
            base = {key: item for key, item in record.items() if key != "mounting"}
            if "mounting" in record:
                identity = fingerprint(base)
                if identity in attachments and attachments[identity] != record["mounting"]:
                    raise ValueError("Receipt identity already has different mounting details")
                attachments[identity] = record["mounting"]
            base_records.append(base)
        if len(attachments) > 2000:
            raise ValueError("Mounting attachment limit is 2000; preserve/archive prior evidence first")
        base_raw = self._encoded({"schema_version": 1, "receipts": base_records})
        mounting_raw = self._encoded({"schema_version": 1, "attachments": attachments})
        # Preserve exact experimental inline bytes before converting their storage.
        if self.path.exists():
            prior = self.path.read_text(encoding="utf-8")
            if any("mounting" in item for item in json.loads(prior)["receipts"]):
                digest = hashlib.sha256(prior.encode("utf-8")).hexdigest()
                recovery = self.path.with_name(self.path.stem + ".inline-" + digest + ".json")
                if recovery.exists() and recovery.read_text(encoding="utf-8") != prior:
                    raise ValueError("Inline mounting recovery differs; existing files preserved")
                if not recovery.exists():
                    self._write(recovery, prior)
        # Attachment first: a failed base commit leaves inert, unreferenced data.
        # Matching requires the complete base receipt hash, never list position.
        if attachments:
            self._write(self.mounting_path, mounting_raw)
        self._write(self.path, base_raw)
        self.records = records
        return receipt

    def _encoded(self, document: object) -> str:
        raw = json.dumps(document, indent=2, allow_nan=False)
        if len(raw.encode("utf-8")) > self.MAX_BYTES:
            raise ValueError("Setup evidence or mounting attachments exceed 2 MiB")
        return raw

    @staticmethod
    def _write(path: Path, raw: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
                name = stream.name
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, path)
            if path.read_text(encoding="utf-8") != raw:
                raise OSError("Setup evidence readback differs")
        finally:
            if name and os.path.exists(name):
                os.unlink(name)

    def latest(self, machine_id: str, group: str) -> SetupReceipt | None:
        return next((r for r in reversed(self.records) if r["machine_id"] == machine_id and r["group"] == group), None)


def _utc_time(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Receipt times must be valid finite UTC dates")
    # Range-check before converting huge integers to avoid overflow in imported records.
    if not 0 <= value <= 253402300799 or not math.isfinite(value):
        raise ValueError("Receipt times must be valid finite UTC dates")
    return float(value)


def evaluate_setup(
    machine_id: str | None,
    snapshots: Mapping[str, object],
    present: Mapping[str, bool],
    store: SetupEvidenceStore,
    now: object,
) -> tuple[ReadinessItem, ...]:
    """All four groups remain evidence checks, never sufficient run authorization."""
    instant = _utc_time(now)
    titles = {
        "stock": "Stock dimensions & placement",
        "workholding": "Fixture & vise mounting",
        "tools": "Physical tooling & lengths",
        "offsets": "Work coordinate alignment",
    }
    targets = {"stock": "Scene", "workholding": "Scene", "tools": "Setup", "offsets": "Overview"}
    items: list[ReadinessItem] = []
    state: ReadinessState
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
        elif instant < receipt["measured_at"]:
            state, detail = (
                "stale",
                "Measurement is dated in the future. Check the receipt timestamp before rechecking.",
            )
        elif instant >= receipt["expires_at"]:
            state, detail = "stale", "Measurement validity interval expired. Recheck the current physical setup."
        else:
            state, detail = "measured", "Operator recorded · " + receipt["method"] + " · " + receipt["source"]
        items.append(ReadinessItem(group, titles[group], state, detail, targets[group], receipt))
    return tuple(items)
