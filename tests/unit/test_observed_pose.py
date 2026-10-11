import pytest

from carveracontroller.addons.machine_simulation.model import MachineSetup
from carveracontroller.machine.observed_pose import ObservedPose


def test_pose_uses_one_packet_and_keeps_tlo_separate():
    pose = ObservedPose.from_packet(
        "Idle",
        {"MPos": [-100, -80, -10, 30], "WPos": [20, 10, 2, 0], "T": [2, 40], "R": [90], "G": [1], "C": [0, 0, 0, 1]},
        10,
    )
    assert pose.machine_mm == (-100, -80, -10)
    assert pose.tool_length_mm == 40
    assert pose.reported_offset_mm == pytest.approx((-90, -100, -12))
    assert pose.fresh(10.5)
    assert not pose.fresh(11)
    assert not pose.fresh(9)
    assert pose.preview_delta_mm(MachineSetup((-100, -80, -10)), (0, 0, 0)) == (0, 0, 0)


def test_missing_or_invalid_packet_cannot_inherit_previous_pose():
    with pytest.raises(ValueError):
        ObservedPose.from_packet("Idle", {"MPos": [1, 2, 3]}, 10)
    with pytest.raises(ValueError):
        ObservedPose.from_packet("Idle", {"MPos": [1, float("nan"), 3], "WPos": [1, 2, 3]}, 10)
    pose = ObservedPose.from_packet("Idle", {"MPos": [1, 2, 3], "WPos": [1, 2, 3], "C": [0, 0, 0, 1]}, 10)
    assert pose.tool is None
    assert pose.tool_length_mm is None


def test_inch_pose_normalizes_xyz_but_not_rotary_or_tlo():
    pose = ObservedPose.from_packet(
        "Idle", {"MPos": [1, 2, 3, 45], "WPos": [0, 1, 2], "T": [2, 40], "C": [0, 0, 1, 0]}, 10
    )
    assert pose.machine_mm == pytest.approx([25.4, 50.8, 76.2])
    assert pose.work_mm == pytest.approx([0, 25.4, 50.8])
    assert pose.rotary_deg == 45
    assert pose.tool_length_mm == 40
    with pytest.raises(ValueError, match="units unavailable"):
        ObservedPose.from_packet("Idle", {"MPos": [1, 2, 3], "WPos": [0, 1, 2]}, 10)
