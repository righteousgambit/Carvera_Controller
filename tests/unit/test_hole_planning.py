import math
from dataclasses import replace

import pytest

from carveracontroller.machine.hole_planning import Hole, HoleTool, HoleWorkflow, ThreadSpec


def workflow(**changes):
    values = {
        "holes": (Hole(10, 20, 8, 6),),
        "tools": {
            "spot": HoleTool(1, "spot", 4, 10, 12, 120),
            "drill": HoleTool(2, "drill", 5, 20, 25),
            "bore": HoleTool(3, "bore", 3, 15, 20),
            "chamfer": HoleTool(4, "chamfer", 8, 10, 15, 90),
            "threadmill": HoleTool(5, "threadmill", 3, 5, 15),
        },
        "thread_spec": ThreadSpec.named("M6"),
        "clearance_z_mm": 5,
        "top_z_mm": 0,
        "floor_z_mm": -12,
        "feed_mm_min": 200,
        "plunge_feed_mm_min": 80,
        "rpm": 10000,
    }
    values.update(changes)
    return HoleWorkflow(**values)


@pytest.mark.parametrize(
    "name,major,pitch,pilot",
    [
        ("#6-32", 3.5052, 25.4 / 32, 2.7051),
        ("#8-32", 4.1656, 25.4 / 32, 3.4544),
        ("#10-24", 4.826, 25.4 / 24, 3.7973),
        ("1/4-20", 6.35, 1.27, 5.1054),
        ("1/4-28", 6.35, 25.4 / 28, 5.4102),
        ("M3", 3, 0.5, 2.5),
        ("M4", 4, 0.7, 3.3),
        ("M5", 5, 0.8, 4.2),
        ("M6", 6, 1, 5),
    ],
)
def test_explicit_thread_specifications(name, major, pitch, pilot):
    spec = ThreadSpec.named(name)
    assert (spec.major_mm, spec.pitch_mm, spec.pilot_mm) == pytest.approx((major, pitch, pilot))
    assert spec.basic_minor_mm < spec.pilot_mm < spec.major_mm


def test_complete_stage_order_tip_depth_and_clearance():
    plan = workflow().plan()
    assert [s.name for s in plan.stages] == ["spot", "drill", "bore", "chamfer", "threadmill"]
    drill = plan.stages[1]
    expected_z = -8 - 5 / (2 * math.tan(math.radians(59)))
    assert f"G1 Z{expected_z:.5f} F80.000" in drill.lines
    for stage in plan.stages:
        for i, line in enumerate(stage.lines):
            if line.startswith("G0 X"):
                assert stage.lines[i - 1] == "G0 Z5.00000"
        assert stage.lines[-1] == "G0 Z5.00000"
    assert plan.gcode().endswith("M5\nM2\n")


def test_thread_helix_radius_pitch_depth_and_handedness():
    right = workflow(radial_passes=1).plan().stages[-1]
    arcs = [line for line in right.lines if line.startswith("G3")]
    assert len(arcs) == 6
    assert "X11.50000 Y20.00000 Z-5.00000 I-1.50000 J0.00000" in arcs[0]
    assert "Z0.00000" in arcs[-1]
    left = workflow(handedness="left", radial_passes=1).plan().stages[-1]
    assert len([line for line in left.lines if line.startswith("G2")]) == 6
    conventional = workflow(climb=False, radial_passes=1).plan().stages[-1]
    assert "Z-6.00000" in [line for line in conventional.lines if line.startswith("G2")][-1]


def test_partial_turn_ends_at_exact_thread_depth():
    stage = workflow(holes=(Hole(10, 20, 8, 5.25),), radial_passes=1).plan().stages[-1]
    arcs = [line for line in stage.lines if line.startswith("G3")]
    assert len(arcs) == 6
    assert "X10.00000 Y21.50000 Z0.00000" in arcs[-1]


@pytest.mark.parametrize(
    "changes",
    [
        {"floor_z_mm": -8},
        {"holes": (Hole(10, 20, 8, 8),)},
        {"fit_allowance_mm": 0.2},
        {"clearance_z_mm": -1},
        {"rpm": float("nan")},
        {"radial_passes": 21},
    ],
)
def test_invalid_floor_bottom_clearance_and_process_rejected(changes):
    with pytest.raises(ValueError):
        workflow(**changes)


def test_tool_reach_pilot_and_pitch_mismatch_rejected():
    original = workflow()
    for tool in (
        replace(original.tools["threadmill"], diameter_mm=5),
        replace(original.tools["threadmill"], thread_pitch_mm=0.7),
        replace(original.tools["threadmill"], reach_mm=5),
    ):
        with pytest.raises(ValueError):
            workflow(tools={**original.tools, "threadmill": tool})
    with pytest.raises(ValueError):
        workflow(
            tools={"drill": replace(original.tools["drill"], diameter_mm=4), "threadmill": original.tools["threadmill"]}
        )
    assert HoleWorkflow.from_dict(original.to_dict()) == original


def test_default_thread_depth_retains_bottom_clearance():
    stage = workflow(holes=(Hole(10, 20, 8),)).plan().stages[-1]
    assert "G1 Z-7.50000 F80.000" in stage.lines


def test_tapping_requires_machine_specific_sync_and_cycle_qualification():
    from carveracontroller.machine.hole_planning import TappingQualification, tapping_preview

    spec = ThreadSpec.named("M6")
    tap = HoleTool(6, "tap", 6, 20, 25, thread_pitch_mm=1)
    args = {"top_z_mm": 0, "clearance_z_mm": 5, "floor_z_mm": -12, "rpm": 500}
    for qualification in (
        None,
        TappingQualification("LinuxCNC", "2.9", "receipt-123", False, True, ("G84",)),
        TappingQualification("LinuxCNC", "2.9", "", True, True, ("G84",)),
    ):
        with pytest.raises(ValueError):
            tapping_preview((Hole(10, 20, 8, 6),), tap, spec, qualification, **args)
    qualified = TappingQualification("LinuxCNC", "2.9", "physical-rigid-tapping-trial-123", True, True, ("G84",))
    program = tapping_preview((Hole(10, 20, 8, 6),), tap, spec, qualified, **args)
    assert "G84 X10.00000 Y20.00000 Z-6.00000 R5.00000 F500.000" in program
    assert "G80" in program
    with pytest.raises(ValueError):
        tapping_preview((Hole(10, 20, 8, 6),), tap, spec, qualified, handedness="left", **args)
