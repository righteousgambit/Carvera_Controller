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
