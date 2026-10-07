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
