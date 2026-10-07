import math
from dataclasses import replace

import pytest

from carveracontroller.machine.cutting_parameters import program_feed_rpm, review_cutting_parameters
from carveracontroller.machine.program_operations import ModalState, ProgramOperations


def state(**changes):
    return replace(
        ModalState(units="G21", feed_mode="G94", motion=1, feed=600, spindle_speed=12000, spindle="M3", tool=2),
        **changes,
    )


def test_kinematics_and_explicit_independent_ceilings():
    r = review_cutting_parameters(6.35, 3, 12000, 600)
    assert r.chip_mm_tooth == pytest.approx(1 / 60)
    assert r.feed_mm_rev == pytest.approx(0.05)
    assert r.surface_m_min == pytest.approx(math.pi * 76.2)
    assert not r.checked_limits and not r.violations
    limited = review_cutting_parameters(6.35, 3, 12000, 600, max_rpm=10000, max_feed_mm_min=500, max_chip_mm_tooth=0.01)
    assert len(limited.violations) == 3 and len(limited.checked_limits) == 3
    boundary = review_cutting_parameters(6.35, 3, 12000, 600, max_rpm=12000, max_feed_mm_min=600)
    assert not boundary.violations
    assert review_cutting_parameters(6.35, 3, 12000, 0).chip_mm_tooth == 0


@pytest.mark.parametrize(
    "args",
    [
        (0, 3, 12000, 600),
        (6, 0, 12000, 600),
        (6, 2.5, 12000, 600),
        (6, True, 12000, 600),
        (6, 3, 0, 600),
        (6, 3, float("nan"), 600),
        (6, 3, 12000, -1),
        (float("inf"), 3, 12000, 600),
    ],
)
def test_invalid_inputs(args):
    with pytest.raises(ValueError):
        review_cutting_parameters(*args)


@pytest.mark.parametrize("name", ["max_rpm", "max_feed_mm_min", "max_chip_mm_tooth"])
def test_invalid_optional_ceilings(name):
    with pytest.raises(ValueError):
        review_cutting_parameters(6, 3, 12000, 600, **{name: -1})


def test_metric_imperial_and_per_revolution_import():
    assert program_feed_rpm(state(), 2) == (600, 12000)
    assert program_feed_rpm(state(units="G20", feed=10), 2) == (254, 12000)
    assert program_feed_rpm(state(units="G20", feed_mode="G95", feed=0.001), 2) == pytest.approx((304.8, 12000))
    assert program_feed_rpm(state(feed_mode="G95", feed=0.05), 2) == (600, 12000)


@pytest.mark.parametrize(
    "changes",
    [
        {"feed_mode": "G93"},
        {"units": None},
        {"motion": 0},
        {"spindle": "M5"},
        {"spindle": None},
        {"spindle_speed": None},
        {"tool": None},
        {"feed": None},
        {"recovery_errors": ("unknown transform",)},
    ],
)
def test_unsafe_or_unknown_import(changes):
    with pytest.raises(ValueError):
        program_feed_rpm(state(**changes), 2)


def test_tool_mismatch_and_css_rejected():
    with pytest.raises(ValueError, match="differs"):
        program_feed_rpm(state(), 3)
    p = ProgramOperations.from_text("G21 G90 G94\nT2 M6\nG96 S200 M3\nG1 X5 F600")
    with pytest.raises(ValueError):
        program_feed_rpm(p.checkpoints[-1].state, 2)


def test_small_chip_ceiling_and_converted_feed_budget():
    r = review_cutting_parameters(0.1, 2, 12000, 1, max_chip_mm_tooth=0.00001)
    assert len(r.violations) == 1
    with pytest.raises(ValueError, match="Converted feed"):
        program_feed_rpm(state(feed_mode="G95", feed=1e8), 2)


def test_declared_engagement_energy_and_independent_demand_limits():
    r = review_cutting_parameters(6, 3, 12000, 600, radial_width_mm=3, axial_depth_mm=2, specific_energy_j_mm3=2)
    assert r.removal_mm3_min == 3600
    assert r.cutting_power_w == 120
    assert r.cutting_torque_nm == pytest.approx(120 / (400 * math.pi))
    limited = review_cutting_parameters(
        6,
        3,
        12000,
        600,
        radial_width_mm=3,
        axial_depth_mm=2,
        specific_energy_j_mm3=2,
        max_cutting_power_w=100,
        max_cutting_torque_nm=0.05,
    )
    assert len(limited.violations) == 2
    equal = review_cutting_parameters(
        6,
        3,
        12000,
        600,
        radial_width_mm=3,
        axial_depth_mm=2,
        specific_energy_j_mm3=2,
        max_cutting_power_w=120,
        max_cutting_torque_nm=r.cutting_torque_nm,
    )
    assert not equal.violations


def test_missing_assumptions_and_zero_engagement_do_not_invent_demand():
    unknown = review_cutting_parameters(6, 3, 12000, 600, max_cutting_power_w=100)
    assert unknown.removal_mm3_min is None and unknown.cutting_power_w is None
    assert "demand unknown" in unknown.checked_limits[0] and not unknown.violations
    removal_only = review_cutting_parameters(6, 3, 12000, 600, radial_width_mm=6, axial_depth_mm=2)
    assert removal_only.removal_mm3_min == 7200 and removal_only.cutting_torque_nm is None
    zero = review_cutting_parameters(6, 3, 12000, 600, radial_width_mm=0, axial_depth_mm=2, specific_energy_j_mm3=2)
    assert zero.removal_mm3_min == zero.cutting_power_w == zero.cutting_torque_nm == 0


@pytest.mark.parametrize(
    "kwargs",
    [
        {"radial_width_mm": 3},
        {"axial_depth_mm": 2},
        {"specific_energy_j_mm3": 2},
        {"radial_width_mm": 7, "axial_depth_mm": 2},
        {"radial_width_mm": 3, "axial_depth_mm": -1},
        {"radial_width_mm": 3, "axial_depth_mm": 2, "specific_energy_j_mm3": 0},
        {"radial_width_mm": True, "axial_depth_mm": 2},
        {"radial_width_mm": 3, "axial_depth_mm": float("inf")},
        {"max_cutting_power_w": -1},
        {"max_cutting_torque_nm": float("nan")},
        {"radial_width_mm": 10000, "axial_depth_mm": 10000, "specific_energy_j_mm3": 1e6},
    ],
)
def test_invalid_engagement_or_demand_assumptions(kwargs):
    with pytest.raises(ValueError):
        review_cutting_parameters(6, 3, 12000, 600, **kwargs)


def test_operation_settings_preserve_units_modes_tools_and_all_source_lines():
    from carveracontroller.machine.cutting_parameters import operation_cutting_review
    from carveracontroller.machine.program_operations import ProgramOperations

    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nT2 M6\nS12000 M3\nG0 X0 Y0 Z0\n"
        "(Operation: Face)\nG1 X5 F600\nG1 X10\nG0 Y1\n"
        "G20 G1 X1 F23.62204724409449\nG21 G95 G1 X30 F0.05\n"
        "G94 G1 X35 F300\nG93 G1 X40 F2\n"
        "(Operation: Finish)\nG94 G1 X45 F100"
    )
    op = next(o for o in program.operations if o.name == "Face")
    review = operation_cutting_review(program, op)
    assert [s.lines for s in review.settings] == [(6, 7), (9,), (10,), (11,)]
    assert [s.feed_mode for s in review.settings] == ["G94", "G94", "G95", "G94"]
    assert [s.units for s in review.settings] == ["G21", "G20", "G21", "G21"]
    assert all(s.tool == 2 for s in review.settings)
    assert review.settings[2].feed_mm_min == 600
    assert review.rapid_lines == 1
    assert review.excluded[0][0] == 12 and "inverse time" in review.excluded[0][1]
    assert sum(len(s.lines) for s in review.settings) + review.rapid_lines + len(review.excluded) == 7


def test_operation_unknown_geometry_and_foreign_identity_rejected():
    from carveracontroller.machine.cutting_parameters import operation_cutting_review
    from carveracontroller.machine.program_operations import ProgramOperations

    program = ProgramOperations.from_text("(Operation: Unknown)\nG1 X5 F600")
    review = operation_cutting_review(program, program.operations[0])
    assert not review.settings and review.excluded == ((2, "Unresolved motion geometry"),)
    other = ProgramOperations.from_text("G1 X10")
    with pytest.raises(ValueError, match="does not belong"):
        operation_cutting_review(program, other.operations[0])


def test_operation_separates_tools_and_excludes_stopped_spindle():
    from carveracontroller.machine.cutting_parameters import operation_cutting_review
    from carveracontroller.machine.program_operations import ProgramOperations

    program = ProgramOperations.from_text(
        "G21 G90 G17 G94 G54\nG0 X0 Y0 Z0\n(Operation: Mixed tools)\n"
        "T1 M6\nS12000 M3\nG1 X1 F600\nT2 M6\nG1 X2\nM5\nG1 X3"
    )
    reviews = [operation_cutting_review(program, operation) for operation in program.operations]
    assert [setting.tool for review in reviews for setting in review.settings] == [1, 2]
    assert reviews[-1].excluded == ((10, "Selected line has stopped or unknown spindle state"),)
