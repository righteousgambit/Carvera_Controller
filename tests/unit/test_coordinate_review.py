import math

import pytest

from carveracontroller.machine.coordinate_review import review_coordinates
from carveracontroller.machine.observed_pose import ObservedPose


def review(**changes):
    args = {
        "point": (10, 20, 30),
        "work_offset": (-180, -120, -110),
        "stock_origin": (0, 0, 0),
        "stock_size": (20, 40, 60),
        "stock_rotation": 0,
        "vise_pivot": (100, 200, 10),
        "vise_offset": (5, 7, 2),
        "vise_rotation": 90,
        "jaw_offset": 3,
        "cad_translation": (-360, -240, -140),
        "pose": None,
        "now": 10,
    }
    args.update(changes)
    return {row.name: row for row in review_coordinates(**args)}


def test_configured_stock_and_cad_vise_frames_have_independent_origins():
    rows = review()
    assert rows["Configured bed point"].point_mm == (-170, -100, -80)
    assert rows["Stock local point"].point_mm == (10, 20, 30)
    # CAD pivot + placement + CAD-to-bed gives (-255, -33, -128).
    # Inverse 90-degree rotation of (85, -67, 48) gives (-67, -85, 48).
    assert rows["Vise pivot-relative point"].point_mm == pytest.approx((-67, -85, 48))
    assert rows["Movable-jaw relative point"].point_mm == pytest.approx((-67, -88, 48))
    assert rows["Fixture frame"].point_mm is None
    assert "Unknown measured" in rows["Fixture frame"].source


def test_rotated_stock_point_inverts_center_rotation_not_wcs():
    rows = review(point=(30, 20, 30), stock_origin=(10, 10, 0), stock_size=(20, 40, 60), stock_rotation=90)
    assert rows["Stock local point"].point_mm == pytest.approx((0, 10, 30))
    assert rows["Configured bed point"].point_mm == (-150, -100, -80)


def test_unknown_geometry_and_stale_pose_never_invent_chain():
    stale = ObservedPose(1, "Idle", (0, 0, 0), (0, 0, 0), 1, 50)
    rows = review(stock_size=None, vise_pivot=None, pose=stale)
    assert rows["Stock local point"].point_mm is None
    assert rows["Vise / jaw point"].point_mm is None
    assert rows["Reported machine/work relation"].point_mm is None
    assert "Reported effective offset" not in rows


def test_same_packet_effective_offset_keeps_tlo_separate():
    pose = ObservedPose(9.9, "Idle", (100, 200, 300), (10, 20, 30), 1, 50, rotation_deg=90, wcs_index=1)
    rows = review(pose=pose)
    assert rows["Reported effective offset"].point_mm == pytest.approx((120, 190, 270))
    assert rows["Reported machine point"].point_mm == (100, 200, 300)
    assert "not added again" in rows["Reported tool length"].relation
    assert "isolate" in rows["Reported effective offset"].relation


def test_entered_point_comparison_uses_reported_rotation_and_same_packet_offset():
    pose = ObservedPose(9.9, "Idle", (100, 200, 300), (10, 20, 30), 1, 50, rotation_deg=90, wcs_index=2)
    rows = review(point=(30, 40, 50), pose=pose)
    # Effective offset (120, 190, 270) plus rotated entered point (-40, 30, 50).
    assert rows["Reported review-point estimate"].point_mm == pytest.approx((80, 220, 320))
    assert rows["Reported versus preview difference"].point_mm == pytest.approx((230, 300, 380))
    assert rows["Reported machine point"].point_mm == (100, 200, 300)
    assert "WCS index 2" in rows["Reported review-point estimate"].relation
    assert "not its cause" in rows["Reported versus preview difference"].relation
    # Reported tool length is already part of packet state; never add it a second time.
    changed = review(
        point=(30, 40, 50), pose=ObservedPose(9.9, "Idle", (100, 200, 300), (10, 20, 30), 1, 75, rotation_deg=90)
    )
    assert changed["Reported review-point estimate"].point_mm == rows["Reported review-point estimate"].point_mm


def test_packet_comparison_requires_fresh_nonfuture_pose_and_keeps_rotary_assumption_explicit():
    for timestamp in (8, 11):
        rows = review(pose=ObservedPose(timestamp, "Idle", (0, 0, 0), (0, 0, 0), 1, 50))
        assert "Reported review-point estimate" not in rows
        assert "Reported versus preview difference" not in rows
    rows = review(pose=ObservedPose(9.9, "Idle", (0, 0, 0), (0, 0, 0), 1, 50, rotary_deg=35))
    assert "A=35°" in rows["Reported review-point estimate"].relation
    assert "no command" in rows["Reported review-point estimate"].relation


@pytest.mark.parametrize(
    "changes",
    [
        {"point": (math.nan, 0, 0)},
        {"work_offset": (0, 0)},
        {"stock_size": (0, 1, 1)},
        {"stock_rotation": math.inf},
        {"vise_rotation": math.nan},
        {"jaw_offset": math.inf},
    ],
)
def test_invalid_frame_data_is_rejected(changes):
    with pytest.raises(ValueError):
        review(**changes)


def test_coordinate_dependencies_keep_unregistered_and_reported_evidence_separate():
    from carveracontroller.machine.coordinate_review import coordinate_paths

    rows = review(pose=ObservedPose(9.9, "Idle", (100, 200, 300), (10, 20, 30), 1, 50))
    paths = {p.review.name: p for p in coordinate_paths(tuple(rows.values()))}
    assert paths["Stock local point"].parent == "Program/WCS point"
    assert paths["Vise pivot-relative point"].parent == "Configured bed point"
    assert paths["Movable-jaw relative point"].parent == "Vise pivot-relative point"
    assert paths["Fixture frame"].parent is None
    assert paths["Fixture frame"].group == "Unregistered fixture"
    assert paths["Reported effective offset"].relationship == "Same-packet derivation"
    assert paths["Reported review-point estimate"].parent == "Reported effective offset"
    assert paths["Reported versus preview difference"].parent == "Reported review-point estimate"
    assert "metadata" in paths["Reported tool length"].relationship
    assert paths["Reported machine point"].group == "Controller packet snapshot"
    missing = review(stock_size=None, vise_pivot=None)
    unknown = {p.review.name: p for p in coordinate_paths(tuple(missing.values()))}
    assert unknown["Stock local point"].relationship == "Unresolved transformation"
    assert unknown["Vise / jaw point"].relationship == "Unresolved transformation"
    with pytest.raises(ValueError, match="unique"):
        coordinate_paths((rows["Program/WCS point"],) * 2)
    with pytest.raises(ValueError, match="Missing coordinate dependency"):
        coordinate_paths((rows["Stock local point"],))


def test_xy_stock_orientation_is_inverted_without_changing_wcs():
    from carveracontroller.addons.manufacturing_simulation import Vec3
    from tests.unit.test_stock_orientation import oracle

    transformed = oracle((23, -32, 41), Vec3(20, 30, 30)).apply(Vec3(14, 19, 11)).tuple
    rows = review(
        point=transformed, stock_origin=(10, 10, 0), stock_size=(20, 40, 60), stock_rotation=41, stock_tilt=(23, -32)
    )
    assert rows["Stock local point"].point_mm == pytest.approx((4, 9, 11))
    assert rows["Configured bed point"].point_mm == pytest.approx(
        tuple(a + b for a, b in zip(transformed, (-180, -120, -110)))
    )
