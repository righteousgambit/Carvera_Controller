import copy
import json
import math

import pytest

from carveracontroller.machine.inspection_plane import export_plane_report, plane_review
from carveracontroller.machine.scene_interaction import SurfaceHit
from carveracontroller.machine.surface_inspection import SurfaceInspectionStore
from carveracontroller.machine.surface_measurement import plan_surface_measurement


def plane_features(tmp_path, points=((-10, -10), (10, -10), (-10, 10), (10, 10)), vertical=False, noise=0):
    store = SurfaceInspectionStore(tmp_path / "plane.json")
    ids = []
    for i, (x, y) in enumerate(points):
        point, normal, triangle = (
            ((0, x, y), (1, 0, 0), ((0, -100, -100), (0, 100, -100), (0, 0, 100)))
            if vertical
            else ((x, y, 0), (0, 0, 1), ((-100, -100, 0), (100, -100, 0), (0, 100, 0)))
        )
        ref = SurfaceHit("stock", "top", i, 10, point, point, normal, triangle)
        plan = plan_surface_measurement(ref, tip_diameter_mm=2, clearance_mm=5, overtravel_mm=1)
        fid = store.create(plan, part="plate-A", name=f"Point {i + 1}", context={"setup": "A"})
        displacement = 0.001 * x + 0.002 * y + (noise if i in (0, 3) else -noise)
        pos = (1 + displacement, x, y) if vertical else (x, y, 1 + displacement)
        store.record(
            fid,
            pos,
            kind="compensated_ball_center",
            source_ref=f"receipt-{i}",
            registration_ref="registration-A",
            calibration_ref="probe-A",
            observed_at="",
        )
        ids.append(fid)
    return store, ids


@pytest.mark.parametrize("vertical", [False, True])
def test_plane_fits_tilted_coordinates_in_any_nominal_orientation(tmp_path, vertical):
    store, ids = plane_features(tmp_path, vertical=vertical)
    before = store.path.read_bytes()
    result = plane_review(store.features, ids[0])
    fit = result["fit"]
    assert fit["tilt_deg"] == pytest.approx(math.degrees(math.atan(math.sqrt(0.001**2 + 0.002**2))))
    assert fit["residual_range_mm"] < 1e-12
    assert fit["nominal_normal_offset_mm"] == pytest.approx(-0.03)
    assert fit["centroid_normal_offset_mm"] == pytest.approx(0)
    assert fit["degrees_of_freedom"] == 1
    assert len(result["samples"]) == 4
    assert result["samples"][0]["receipt"]["observed_at"] == ""
    assert result["samples"][0]["contact_mm"][0 if vertical else 2] == pytest.approx(-0.03)
    assert store.path.read_bytes() == before


def test_residual_range_is_not_plane_tilt_or_nominal_deviation(tmp_path):
    store, ids = plane_features(tmp_path, noise=0.02)
    result = plane_review(store.features, ids[0])
    assert result["fit"]["residual_range_mm"] == pytest.approx(0.04 / math.sqrt(1 + 0.001**2 + 0.002**2))
    assert sum(row["residual_mm"] for row in result["samples"]) == pytest.approx(0, abs=1e-12)


def test_latest_raw_receipt_is_excluded_without_falling_back_to_older_fit(tmp_path):
    store, ids = plane_features(tmp_path)
    store.record(
        ids[0],
        (0, 0, 999),
        kind="raw_trigger",
        source_ref="raw",
        registration_ref="registration-A",
        calibration_ref="probe-A",
    )
    latest = plane_review(store.features, ids[0])
    assert len(latest["samples"]) == 3
    assert latest["excluded"][0]["reason"].startswith("Raw trigger")
    assert latest["fit"]["degrees_of_freedom"] == 0
    earliest = plane_review(store.features, ids[0], "earliest")
    assert len(earliest["samples"]) == 4
    assert not earliest["excluded"]


def test_mismatched_registration_or_compensation_cannot_be_joined(tmp_path):
    store, ids = plane_features(tmp_path)
    store.record(
        ids[-1],
        (10, 10, 1),
        kind="compensated_ball_center",
        source_ref="other",
        registration_ref="other-registration",
        calibration_ref="probe-A",
    )
    with pytest.raises(ValueError, match="different registration"):
        plane_review(store.features, ids[0])


@pytest.mark.parametrize(
    "points", [((0, 0), (1, 0), (2, 0)), ((0, 0), (0, 0), (0, 0)), ((0, 0), (1, 1e-9), (2, 0)), ((0, 0), (1, 1))]
)
def test_no_plane_is_invented_for_insufficient_or_collinear_spread(tmp_path, points):
    store, ids = plane_features(tmp_path, points=points)
    report = plane_review(store.features, ids[0])
    assert report["fit"] is None
    assert report["reason"]


def test_other_setup_groups_and_missing_references_remain_explicit(tmp_path):
    store, ids = plane_features(tmp_path)
    f = store.get(ids[0])
    other = store.create(
        plan_surface_measurement(
            SurfaceHit(
                "stock", "top", 0, 10, (0, 0, 0), (0, 0, 0), (0, 0, 1), ((-100, -100, 0), (100, -100, 0), (0, 100, 0))
            ),
            tip_diameter_mm=2,
            clearance_mm=5,
            overtravel_mm=1,
        ),
        part="other-part",
        name="Other",
        context=f["context"],
    )
    store.record(
        ids[-1],
        (10, 10, 1),
        kind="compensated_ball_center",
        source_ref="unregistered",
        registration_ref="",
        calibration_ref="probe-A",
    )
    report = plane_review(store.features, ids[0])
    assert report["other_group_features"] == 1
    assert other not in [row["feature_id"] for row in report["samples"]]
    assert len(report["excluded"]) == 1
    assert report["excluded"][0]["receipt_id"] == store.get(ids[-1])["samples"][-1]["id"]


def test_export_retains_exact_inputs_and_rejects_changed_fitted_values(tmp_path):
    store, ids = plane_features(tmp_path)
    report = plane_review(store.features, ids[0])
    target = tmp_path / "review.cvplane"
    receipt = export_plane_report(report, str(target))
    assert receipt["bytes"] == target.stat().st_size
    assert json.loads(target.read_bytes())["report"] == report
    original = target.read_bytes()
    changed = copy.deepcopy(report)
    changed["fit"]["residual_range_mm"] = 999
    with pytest.raises(ValueError, match="no longer matches"):
        export_plane_report(changed, str(target))
    assert target.read_bytes() == original


def test_invalid_policy_and_nominal_digest_rejected(tmp_path):
    store, ids = plane_features(tmp_path)
    with pytest.raises(ValueError, match="latest or earliest"):
        plane_review(store.features, ids[0], "best")
    corrupt = copy.deepcopy(store.features)
    corrupt[0]["plan"]["tip_diameter_mm"] = 3
    with pytest.raises(ValueError, match="identity mismatch"):
        plane_review(corrupt, ids[0])


@pytest.mark.parametrize("limit", [-0.01, True, float("inf")])
def test_invalid_export_limits_reject_before_mutating_destination(tmp_path, limit):
    store, ids = plane_features(tmp_path)
    report = plane_review(store.features, ids[0])
    target = tmp_path / "rejected.cvplane"
    with pytest.raises(ValueError):
        export_plane_report(report, str(target), limit)
    assert not target.exists()
