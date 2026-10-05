"""Retained nominal surface inspections with explicit measurement provenance."""

import copy
import hashlib
import json
import math
import os
import statistics
import tempfile
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from carveracontroller.machine.scene_interaction import SurfaceHit, cross, dot, ray, subtract, triangle_distance, vector
from carveracontroller.machine.surface_measurement import plan_surface_measurement


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def text(value, title, required=True):
    if not isinstance(value, str) or len(value) > 2048 or (required and not value.strip()):
        raise ValueError(f"{title} is required and must be bounded text")
    return value.strip()


def number(value, title):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"{title} must be a finite number")
    return value


def definition(plan):
    return {
        "reference": asdict(plan.reference),
        "tip_diameter_mm": plan.tip_radius_mm * 2,
        "clearance_mm": math.dist(plan.approach_mm, plan.contact_center_mm),
        "overtravel_mm": math.dist(plan.search_limit_mm, plan.contact_center_mm),
        "direction": plan.direction,
        "flip": sum(a * b for a, b in zip(plan.outward_normal, plan.reference.normal)) < 0,
    }


def restore_plan(value):
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
        ref[key] = vector(ref[key])
    if len(ref["triangle"]) != 3:
        raise ValueError("Reference requires three triangle vertices")
    ref["triangle"] = tuple(vector(p) for p in ref["triangle"])
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
    return plan_surface_measurement(SurfaceHit(**ref), **{k: v for k, v in value.items() if k != "reference"})


def sample_result(feature, sample):
    """Only declared registered, compensated centers can be compared locally."""
    if sample["kind"] != "compensated_ball_center" or not sample["registration_ref"] or not sample["calibration_ref"]:
        return {"deviation_mm": None, "state": "unevaluated"}
    deviation = restore_plan(feature["plan"]).normal_deviation_mm(sample["position_mm"])
    number(deviation, "Normal deviation")
    lower, upper = feature["limits_mm"]
    state = (
        "untoleranced"
        if lower is None
        else "within_declared_limits"
        if lower <= deviation <= upper
        else "outside_declared_limits"
    )
    return {"deviation_mm": deviation, "state": state}


def summary(feature):
    results = [sample_result(feature, s) for s in feature["samples"]]
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

    def __init__(self, path=None):
        self.path = Path(path or Path.home() / ".carvera/surface-inspections.json")
        self.features = []
        self.error = None
        self._file_hash = None
        try:
            if self.path.exists():
                if self.path.stat().st_size > self.MAX_BYTES:
                    raise ValueError("Inspection file exceeds size limit")
                payload = self.path.read_bytes()
                self._file_hash = hashlib.sha256(payload).hexdigest()
                data = json.loads(payload, object_pairs_hook=self._object)
                self.features = self.validate(data)
        except (OSError, ValueError, TypeError, KeyError, OverflowError) as exc:
            self.error = str(exc)

    @staticmethod
    def _object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate inspection JSON key")
            result[key] = value
        return result

    @classmethod
    def validate(cls, data):
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
            if set(f) != {
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
            restore_plan(f["plan"])
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
                if set(sample) != {
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
                vector(sample["position_mm"])
                number(sample["recorded_at"], "Receipt time")
                if sample["frame"] != "nominal_component_machine_mm" or sample["source_class"] != "operator_entered":
                    raise ValueError("Unknown receipt coordinate frame or evidence class")
                if sample["kind"] not in ("compensated_ball_center", "raw_trigger"):
                    raise ValueError("Unknown measurement coordinate kind")
                sample_result(f, sample)
        # Normalize the public representation to JSON types so disk/bundle
        # roundtrips retain exact equality as well as canonical identity.
        return json.loads(canonical(features))

    def _save(self, features):
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

    def create(self, plan, *, part, name, context, limits=(None, None)):
        plan_data = definition(plan)
        context = json.loads(canonical(context))
        feature = {
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

    def get(self, feature_id):
        feature = next((f for f in self.features if f["id"] == feature_id), None)
        if feature is None:
            raise ValueError("Inspection feature not found")
        return copy.deepcopy(feature)

    def record(
        self, feature_id, position_mm, *, kind, source_ref, registration_ref="", calibration_ref="", observed_at=""
    ):
        features = copy.deepcopy(self.features)
        feature = next((f for f in features if f["id"] == feature_id), None)
        if feature is None:
            raise ValueError("Inspection feature not found")
        sample = {
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
