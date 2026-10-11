import pytest

from carveracontroller.machine.exploded_view import explosion_offset, validate_explosion


def test_assembly_offsets_preserve_spindle_cutter_and_leave_markers_at_nominal_pose():
    assert explosion_offset("spindle", 25, "Preview") == explosion_offset("cutter", 25, "Preview") == (50, 0, 75)
    assert explosion_offset("fixture", 25, "Preview") == (0, 0, 25)
    assert explosion_offset("workholding", 25, "Preview") == (0, 0, 50)
    assert explosion_offset("stock", 25, "Preview") == (0, 0, 75)
    assert explosion_offset("live_pose", 25, "Preview") == (0, 0, 0)
    for mode in ("Live", "Compare"):
        assert explosion_offset("spindle", 25, mode) == (0, 0, 0)


@pytest.mark.parametrize("value", [-1, 101, True, float("nan"), float("inf"), "25"])
def test_invalid_separation_is_rejected(value):
    with pytest.raises(ValueError):
        validate_explosion(value)
