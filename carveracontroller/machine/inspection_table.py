"""Read-only ordering and spreadsheet exchange of identity-bound inspection receipts."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from carveracontroller.machine.surface_inspection import InspectionFeature, InspectionSample, SampleResult

ReceiptRow = tuple[InspectionSample, SampleResult]
ORDERS = (
    "Receipt order",
    "Newest recorded",
    "Source A–Z",
    "Deviation low–high",
    "Deviation high–low",
    "Largest absolute deviation",
)


def ordered_receipts(rows: Iterable[ReceiptRow], order: str) -> list[ReceiptRow]:
    """Stable ties retain input order. Unevaluated values always remain last."""
    items = list(rows)
    if order not in ORDERS:
        raise ValueError("Unknown receipt order")
    if order == "Receipt order":
        return items
    if order == "Newest recorded":
        return sorted(items, key=lambda row: row[0]["recorded_at"], reverse=True)
    if order == "Source A–Z":
        return sorted(items, key=lambda row: row[0]["source_ref"].casefold())
    evaluated = [row for row in items if row[1]["deviation_mm"] is not None]
    unknown = [row for row in items if row[1]["deviation_mm"] is None]

    def key(row: ReceiptRow) -> float:
        value = row[1]["deviation_mm"]
        assert value is not None
        return abs(value) if order == "Largest absolute deviation" else value

    return sorted(evaluated, key=key, reverse=order != "Deviation low–high") + unknown


def receipts_tsv(feature: InspectionFeature, rows: Iterable[ReceiptRow], *, draft: bool = False) -> str:
    """Keep original precision, unknowns and references; exporting grants no accuracy claim."""
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, delimiter="\t", lineterminator="\n")
    writer.writerow(
        (
            "feature_id",
            "part",
            "feature",
            "nominal_sha256",
            "receipt_id",
            "retention",
            "x_mm",
            "y_mm",
            "z_mm",
            "deviation_mm",
            "comparison",
            "kind",
            "frame",
            "source_class",
            "source_ref",
            "registration_ref",
            "calibration_ref",
            "observed_at",
            "recorded_at_unix",
            "lower_limit_mm",
            "upper_limit_mm",
        )
    )
    for sample, result in rows:
        writer.writerow(
            (
                feature["id"],
                feature["part"],
                feature["name"],
                feature["nominal_sha256"],
                sample["id"],
                "proposed" if draft else "retained",
                *sample["position_mm"],
                result["deviation_mm"],
                result["state"],
                sample["kind"],
                sample["frame"],
                sample["source_class"],
                sample["source_ref"],
                sample["registration_ref"],
                sample["calibration_ref"],
                sample["observed_at"],
                None if draft else sample["recorded_at"],
                *feature["limits_mm"],
            )
        )
    return stream.getvalue()
