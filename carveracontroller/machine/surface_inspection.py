"""Retained nominal surface inspections with explicit measurement provenance."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import statistics
import tempfile
import time
import uuid
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Literal, TypedDict, cast

from carveracontroller.machine.scene_interaction import (
    SurfaceHit,
    Vec3,
    cross,
    dot,
    ray,
    subtract,
    triangle_distance,
    vector,
)
from carveracontroller.machine.surface_measurement import SurfaceMeasurementPlan, plan_surface_measurement


class SurfaceReference(TypedDict):
    component: str
    group: str
    triangle_index: int
    distance_mm: float
    display_point_mm: Sequence[float]
    component_point_mm: Sequence[float]
    normal: Sequence[float]
    triangle: Sequence[Sequence[float]]


class SurfacePlanDefinition(TypedDict):
    reference: SurfaceReference
    tip_diameter_mm: float
    clearance_mm: float
    overtravel_mm: float
    direction: Sequence[float]
    flip: bool


class InspectionSample(TypedDict):
    id: str
    position_mm: Sequence[float]
    kind: Literal["compensated_ball_center", "raw_trigger"]
    source_ref: str
    registration_ref: str
    calibration_ref: str
    observed_at: str
    recorded_at: float
    frame: Literal["nominal_component_machine_mm"]
    source_class: Literal["operator_entered"]


class InspectionFeature(TypedDict):
    id: str
    part: str
    name: str
    created_at: float
    plan: SurfacePlanDefinition
    context: dict[str, object]
    nominal_sha256: str
    limits_mm: Sequence[float | None]
    samples: list[InspectionSample]


class SampleResult(TypedDict):
    deviation_mm: float | None
    state: Literal["unevaluated", "untoleranced", "within_declared_limits", "outside_declared_limits"]


class InspectionSummary(TypedDict):
    recorded: int
    evaluated: int
    unevaluated: int
    outside: int
    mean_mm: float | None
    range_mm: float | None
    sample_stdev_mm: float | None


def _vector(value: object) -> Vec3:
    if not isinstance(value, (tuple, list)) or len(value) != 3:
        raise ValueError("Inspection vectors require three finite numbers")
    return vector([number(item, "Vector component") for item in value])


def read_bounded(path: Path, maximum: int) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(maximum + 1)
    if len(payload) > maximum:
        raise ValueError("Inspection file exceeds size limit")
    return payload


def canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value: object, title: str, required: bool = True) -> str:
    if not isinstance(value, str) or len(value) > 2048 or (required and not value.strip()):
        raise ValueError(f"{title} is required and must be bounded text")
    return value.strip()


def number(value: object, title: str) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{title} must be a finite number")
    try:
        result = float(cast(float, value))
    except (OverflowError, ValueError):
        raise ValueError(f"{title} must be a finite number") from None
    if not math.isfinite(result):
        raise ValueError(f"{title} must be a finite number")
    return result


def definition(plan: SurfaceMeasurementPlan) -> SurfacePlanDefinition:
    return {
        "reference": cast(SurfaceReference, asdict(plan.reference)),
        "tip_diameter_mm": plan.tip_radius_mm * 2,
        "clearance_mm": math.dist(plan.approach_mm, plan.contact_center_mm),
        "overtravel_mm": math.dist(plan.search_limit_mm, plan.contact_center_mm),
        "direction": plan.direction,
        "flip": sum(a * b for a, b in zip(plan.outward_normal, plan.reference.normal)) < 0,
    }


def restore_plan(value: object) -> SurfaceMeasurementPlan:
    if not isinstance(value, dict) or set(value) != {
        "reference",
        "tip_diameter_mm",
        "clearance_mm",
        "overtravel_mm",
        "direction",
        "flip",
    }:
        raise ValueError("Invalid surface plan fields")
    ref = value["reference"]
    if not isinstance(ref, dict) or set(ref) != set(SurfaceHit.__dataclass_fields__):
        raise ValueError("Invalid nominal surface reference")
    ref = dict(ref)
    for key in ("component", "group"):
        text(ref[key], key)
    if type(ref["triangle_index"]) is not int or ref["triangle_index"] < 0:
        raise ValueError("Invalid triangle index")
    if number(ref["distance_mm"], "Pick distance") < 0:
        raise ValueError("Invalid pick distance")
    for key in ("display_point_mm", "component_point_mm", "normal"):
        ref[key] = _vector(ref[key])
    if not isinstance(ref["triangle"], (list, tuple)) or len(ref["triangle"]) != 3:
        raise ValueError("Reference requires three triangle vertices")
    ref["triangle"] = tuple(_vector(p) for p in ref["triangle"])
    a, b, c = ref["triangle"]
    _, winding = ray((0, 0, 0), cross(subtract(b, a), subtract(c, a)))
    _, normal = ray((0, 0, 0), ref["normal"])
    if dot(winding, normal) < 1 - 1e-6:
        raise ValueError("Reference normal does not match source triangle winding")
    origin = tuple(p + n for p, n in zip(ref["component_point_mm"], normal))
    distance = triangle_distance(origin, tuple(-n for n in normal), ref["triangle"])
    if distance is None or abs(distance - 1) > 1e-6:
        raise ValueError("Nominal point is outside its source triangle")
    if type(value["flip"]) is not bool:
        raise ValueError("Invalid normal reversal")
    reference = SurfaceHit(
        cast(str, ref["component"]),
        cast(str, ref["group"]),
        ref["triangle_index"],
        number(ref["distance_mm"], "Pick distance"),
        ref["display_point_mm"],
        ref["component_point_mm"],
        ref["normal"],
        (_vector(ref["triangle"][0]), _vector(ref["triangle"][1]), _vector(ref["triangle"][2])),
    )
    return plan_surface_measurement(
        reference,
        tip_diameter_mm=number(value["tip_diameter_mm"], "Tip diameter"),
        clearance_mm=number(value["clearance_mm"], "Clearance"),
        overtravel_mm=number(value["overtravel_mm"], "Overtravel"),
        direction=_vector(value["direction"]),
        flip=value["flip"],
    )


def sample_result(feature: InspectionFeature, sample: InspectionSample) -> SampleResult:
    """Only declared registered, compensated centers can be compared locally."""
    return _sample_result(feature, sample, restore_plan(feature["plan"]))


def _sample_result(feature: InspectionFeature, sample: InspectionSample, plan: SurfaceMeasurementPlan) -> SampleResult:
    if sample["kind"] != "compensated_ball_center" or not sample["registration_ref"] or not sample["calibration_ref"]:
        return {"deviation_mm": None, "state": "unevaluated"}
    deviation = plan.normal_deviation_mm(sample["position_mm"])
    number(deviation, "Normal deviation")
    lower, upper = feature["limits_mm"]
    if lower is not None and upper is None:
        raise ValueError("Supply both tolerance limits or leave both empty")
    state: Literal["unevaluated", "untoleranced", "within_declared_limits", "outside_declared_limits"] = (
        "untoleranced"
        if lower is None
        else "within_declared_limits"
        if lower <= deviation <= cast(float, upper)
        else "outside_declared_limits"
    )
    return {"deviation_mm": deviation, "state": state}


def sample_results(feature: InspectionFeature) -> list[SampleResult]:
    """Calculate a retained series using one restored nominal geometry."""
    plan = restore_plan(feature["plan"])
    return [_sample_result(feature, sample, plan) for sample in feature["samples"]]


def summary(feature: InspectionFeature) -> InspectionSummary:
    results = sample_results(feature)
    values = [r["deviation_mm"] for r in results if r["deviation_mm"] is not None]
    return {
        "recorded": len(results),
        "evaluated": len(values),
        "unevaluated": len(results) - len(values),
        "outside": sum(r["state"] == "outside_declared_limits" for r in results),
        "mean_mm": statistics.mean(values) if values else None,
        "range_mm": max(values) - min(values) if values else None,
        "sample_stdev_mm": statistics.stdev(values) if len(values) > 1 else None,
    }


class SurfaceInspectionStore:
    MAX_BYTES = 8 * 1024 * 1024
    MAX_FEATURES = 1000
    MAX_SAMPLES = 1000

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or Path.home() / ".carvera/surface-inspections.json")
        self.features: list[InspectionFeature] = []
        self.error: str | None = None
        self._file_hash: str | None = None
        try:
            if self.path.exists():
                payload = read_bounded(self.path, self.MAX_BYTES)
                self._file_hash = hashlib.sha256(payload).hexdigest()
                data = json.loads(payload, object_pairs_hook=self._object)
                self.features = self.validate(data)
        except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError) as exc:
            self.error = str(exc)

    @staticmethod
    def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate inspection JSON key")
            result[key] = value
        return result

    @classmethod
    def validate(cls, data: object) -> list[InspectionFeature]:
        if (
            not isinstance(data, dict)
            or set(data) != {"schema", "features"}
            or type(data["schema"]) is not int
            or data["schema"] != 1
        ):
            raise ValueError("Unsupported surface inspection format")
        features = data["features"]
        if not isinstance(features, list) or len(features) > cls.MAX_FEATURES:
            raise ValueError("Invalid feature count")
        ids = set()
        for f in features:
            if not isinstance(f, dict) or set(f) != {
                "id",
                "part",
                "name",
                "created_at",
                "plan",
                "context",
                "nominal_sha256",
                "limits_mm",
                "samples",
            }:
                raise ValueError("Invalid inspection feature fields")
            for key in ("id", "part", "name"):
                text(f[key], key)
            if f["id"] in ids:
                raise ValueError("Duplicate inspection identity")
            ids.add(f["id"])
            number(f["created_at"], "Feature time")
            plan = restore_plan(f["plan"])
            if not isinstance(f["context"], dict) or f["nominal_sha256"] != digest(
                {"plan": f["plan"], "context": f["context"]}
            ):
                raise ValueError("Nominal/context identity mismatch")
            limits = f["limits_mm"]
            if not isinstance(limits, (list, tuple)) or len(limits) != 2:
                raise ValueError("Invalid tolerance limits")
            if limits != [None, None] and limits != (None, None):
                if any(v is None for v in limits):
                    raise ValueError("Supply both tolerance limits or leave both empty")
                if number(limits[0], "Lower limit") > number(limits[1], "Upper limit"):
                    raise ValueError("Lower limit exceeds upper limit")
            if not isinstance(f["samples"], list) or len(f["samples"]) > cls.MAX_SAMPLES:
                raise ValueError("Invalid sample count")
            sample_ids = set()
            for sample in f["samples"]:
                if not isinstance(sample, dict) or set(sample) != {
                    "id",
                    "position_mm",
                    "kind",
                    "source_ref",
                    "registration_ref",
                    "calibration_ref",
                    "observed_at",
                    "recorded_at",
                    "frame",
                    "source_class",
                }:
                    raise ValueError("Invalid measurement receipt fields")
                for key in ("id", "source_ref", "registration_ref", "calibration_ref", "observed_at"):
                    text(sample[key], key, required=key in ("id", "source_ref"))
                if sample["id"] in sample_ids:
                    raise ValueError("Duplicate sample identity")
                sample_ids.add(sample["id"])
                _vector(sample["position_mm"])
                number(sample["recorded_at"], "Receipt time")
                if sample["frame"] != "nominal_component_machine_mm" or sample["source_class"] != "operator_entered":
                    raise ValueError("Unknown receipt coordinate frame or evidence class")
                if sample["kind"] not in ("compensated_ball_center", "raw_trigger"):
                    raise ValueError("Unknown measurement coordinate kind")
                _sample_result(cast(InspectionFeature, f), cast(InspectionSample, sample), plan)
        # Normalize the public representation to JSON types so disk/bundle
        # roundtrips retain exact equality as well as canonical identity.
        return cast(list[InspectionFeature], json.loads(canonical(features)))

    def _save(self, features: list[InspectionFeature]) -> None:
        if self.error:
            raise ValueError("Inspection file needs repair before writing: " + self.error)
        data = {"schema": 1, "features": features}
        validated = self.validate(data)
        payload = canonical(data).encode()
        if len(payload) > self.MAX_BYTES:
            raise ValueError("Inspection file exceeds size limit")
        current = hashlib.sha256(self.path.read_bytes()).hexdigest() if self.path.exists() else None
        if current != self._file_hash:
            raise ValueError("Inspection file changed externally · reopen before saving")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".surface-inspections-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        self.features = validated
        self._file_hash = hashlib.sha256(payload).hexdigest()

    def create(
        self,
        plan: SurfaceMeasurementPlan,
        *,
        part: str,
        name: str,
        context: dict[str, object],
        limits: Sequence[float | None] = (None, None),
    ) -> str:
        plan_data = definition(plan)
        context = json.loads(canonical(context))
        feature: InspectionFeature = {
            "id": str(uuid.uuid4()),
            "part": part,
            "name": name,
            "created_at": time.time(),
            "plan": plan_data,
            "context": context,
            "nominal_sha256": digest({"plan": plan_data, "context": context}),
            "limits_mm": list(limits),
            "samples": [],
        }
        self._save([*self.features, feature])
        return feature["id"]

    def get(self, feature_id: str) -> InspectionFeature:
        feature = next((f for f in self.features if f["id"] == feature_id), None)
        if feature is None:
            raise ValueError("Inspection feature not found")
        return copy.deepcopy(feature)

    def record(
        self,
        feature_id: str,
        position_mm: Sequence[float],
        *,
        kind: Literal["compensated_ball_center", "raw_trigger"],
        source_ref: str,
        registration_ref: str = "",
        calibration_ref: str = "",
        observed_at: str = "",
    ) -> str:
        features = copy.deepcopy(self.features)
        feature = next((f for f in features if f["id"] == feature_id), None)
        if feature is None:
            raise ValueError("Inspection feature not found")
        sample: InspectionSample = {
            "id": str(uuid.uuid4()),
            "position_mm": vector(position_mm),
            "kind": kind,
            "source_ref": source_ref,
            "registration_ref": registration_ref,
            "calibration_ref": calibration_ref,
            "observed_at": observed_at,
            "recorded_at": time.time(),
            "frame": "nominal_component_machine_mm",
            "source_class": "operator_entered",
        }
        feature["samples"].append(sample)
        self._save(features)
        return sample["id"]
