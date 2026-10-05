"""Reviewed, atomic operator-entered measurement tables; no machine transport."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import time
import uuid
from dataclasses import dataclass
from typing import Literal, cast

from carveracontroller.machine.quantities import parse_quantity
from carveracontroller.machine.surface_inspection import (
    InspectionFeature,
    InspectionSample,
    SurfaceInspectionStore,
    canonical,
    digest,
    text,
)

REQUIRED = {"x", "y", "z", "source_ref"}
OPTIONAL = {"kind", "registration_ref", "calibration_ref", "observed_at"}
MAX_INPUT_BYTES = 256 * 1024


@dataclass(frozen=True)
class InspectionBatchReview:
    feature_id: str
    feature_sha256: str
    input_sha256: str
    records_json: str
    records_sha256: str
    count: int


def batch_feature(feature: InspectionFeature, review: InspectionBatchReview) -> InspectionFeature:
    """Return only reviewed additions for the comparison UI, preserving nominal."""
    if feature["id"] != review.feature_id or digest(feature) != review.feature_sha256:
        raise ValueError("Inspection feature changed after review · review the table again")
    if hashlib.sha256(review.records_json.encode()).hexdigest() != review.records_sha256:
        raise ValueError("Reviewed batch changed")
    records = json.loads(review.records_json)
    if not isinstance(records, list) or not records or len(records) != review.count:
        raise ValueError("Invalid reviewed batch count")
    candidate = {**feature, "samples": records}
    return SurfaceInspectionStore.validate({"schema": 1, "features": [candidate]})[0]


def review_batch(
    feature: InspectionFeature,
    content: str,
    *,
    separator: Literal["CSV", "TSV"],
    default_kind: Literal["compensated_ball_center", "raw_trigger"],
) -> InspectionBatchReview:
    if separator not in ("CSV", "TSV") or default_kind not in ("compensated_ball_center", "raw_trigger"):
        raise ValueError("Choose the table separator and coordinate kind")
    if len(content.encode()) > MAX_INPUT_BYTES:
        raise ValueError("Measurement table exceeds 256 KiB")
    rows = csv.reader(io.StringIO(content), delimiter="," if separator == "CSV" else "\t", strict=True)
    try:
        header = [value.strip().casefold() for value in next(rows)]
    except (StopIteration, csv.Error) as exc:
        raise ValueError("Supply a header and measurement rows") from exc
    if len(set(header)) != len(header) or not set(header) >= REQUIRED or set(header) - REQUIRED - OPTIONAL:
        raise ValueError(
            "Headers require x, y, z, source_ref; optional kind, registration_ref, calibration_ref, observed_at"
        )
    records: list[InspectionSample] = []
    errors = []
    try:
        for row in rows:
            if not row or not any(cell.strip() for cell in row):
                continue
            if len(records) + len(errors) >= SurfaceInspectionStore.MAX_SAMPLES:
                raise ValueError("Measurement table exceeds 1000 rows")
            try:
                if len(row) != len(header):
                    raise ValueError("Column count does not match header")
                values = dict(zip(header, row))
                kind = values.get("kind", "").strip() or default_kind
                if kind not in ("compensated_ball_center", "raw_trigger"):
                    raise ValueError("kind must be compensated_ball_center or raw_trigger")
                records.append(
                    {
                        "id": str(uuid.uuid4()),
                        "position_mm": [
                            float(parse_quantity(values[axis], minimum=-1000000, maximum=1000000)) for axis in "xyz"
                        ],
                        "kind": cast(Literal["compensated_ball_center", "raw_trigger"], kind),
                        "source_ref": text(values["source_ref"], "source_ref"),
                        "registration_ref": text(
                            values.get("registration_ref", ""), "registration_ref", required=False
                        ),
                        "calibration_ref": text(values.get("calibration_ref", ""), "calibration_ref", required=False),
                        "observed_at": text(values.get("observed_at", ""), "observed_at", required=False),
                        "recorded_at": 0.0,
                        "frame": "nominal_component_machine_mm",
                        "source_class": "operator_entered",
                    }
                )
            except ValueError as exc:
                errors.append(f"Line {rows.line_num}: {exc}")
    except csv.Error as exc:
        raise ValueError(f"Invalid table near line {rows.line_num}: {exc}") from exc
    if errors:
        raise ValueError(f"{len(errors)} invalid rows · no records retained\n" + "\n".join(errors[:10]))
    if not records:
        raise ValueError("Supply at least one measurement row")
    if len(feature["samples"]) + len(records) > SurfaceInspectionStore.MAX_SAMPLES:
        raise ValueError("Batch would exceed the feature's 1000 retained receipts")
    SurfaceInspectionStore.validate(
        {"schema": 1, "features": [{**feature, "samples": [*feature["samples"], *records]}]}
    )
    payload = canonical(records)
    return InspectionBatchReview(
        feature["id"],
        digest(feature),
        hashlib.sha256(content.encode()).hexdigest(),
        payload,
        hashlib.sha256(payload.encode()).hexdigest(),
        len(records),
    )


def apply_batch(store: SurfaceInspectionStore, review: InspectionBatchReview) -> list[str]:
    current = store.get(review.feature_id)
    additions = batch_feature(current, review)["samples"]
    recorded_at = time.time()
    for receipt in additions:
        receipt["recorded_at"] = recorded_at
    candidate: InspectionFeature = {**current, "samples": [*current["samples"], *additions]}
    features = [candidate if feature["id"] == current["id"] else feature for feature in store.features]
    store._save(features)
    return [receipt["id"] for receipt in additions]
