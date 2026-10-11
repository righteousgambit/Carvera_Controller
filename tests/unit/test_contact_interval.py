"""Analytic entry/exit, independent pose oracle and ordered-stock witnesses."""

import random
from dataclasses import replace
from math import sqrt

import pytest

from carveracontroller.addons.manufacturing_simulation import (
    AABB,
    CollisionObstacle,
    CollisionScene,
    SimulationSegment,
    StockVolume,
    SweptTool,
    ToolGeometry,
    Vec3,
    simulate,
)
from carveracontroller.addons.manufacturing_simulation.clearance import analyze_clearance
from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope

TOOL = ToolGeometry(2, 2, 2, 5)


def box(low, high):
    return AABB(Vec3(*low), Vec3(*high))


def motion(start, end, tool=TOOL):
    return SweptTool(Vec3(*start), Vec3(*end), tool)


def test_entry_exit_between_clear_endpoints_and_reversal():
    sweep = motion((-10, 0, 0), (10, 0, 0))
    obstacle = box((-1, -1, 1), (1, 1, 2))
    assert sweep.contact_interval(sweep.sections()[0], obstacle) == pytest.approx((0.4, 0.6))
    reverse = SweptTool(sweep.end, sweep.start, TOOL)
    assert reverse.contact_interval(sweep.sections()[0], obstacle) == pytest.approx((0.4, 0.6))
    assert motion((-10, 0, 0), (-10, 0, 0)).contact_interval(sweep.sections()[0], obstacle) is None
    assert motion((10, 0, 0), (10, 0, 0)).contact_interval(sweep.sections()[0], obstacle) is None


def test_round_corner_root_and_translation_invariance():
    for origin in (0, 1e6):
        sweep = motion((origin - 5, -5, 0), (origin + 5, 5, 0))
        interval = sweep.contact_interval(sweep.sections()[0], box((origin, 0, 0), (origin + 2, 2, 1)))
        assert interval == pytest.approx(((5 - 1 / sqrt(2)) / 10, (7 + 1 / sqrt(2)) / 10))


def test_axial_overlap_controls_entry_exit_and_single_point_contact():
    sweep = motion((0, 0, -10), (0, 0, 10))
    assert sweep.contact_interval(sweep.sections()[0], box((-1, -1, 0), (1, 1, 1))) == pytest.approx((0.4, 0.55))
    ending = motion((0, 0, -10), (0, 0, -2))
    assert ending.contact_interval(ending.sections()[0], box((-1, -1, 0), (1, 1, 1))) == (1, 1)
    miss = motion((-10, 0, -10), (10, 0, 10))
    assert miss.contact_interval(miss.sections()[0], box((-9, -1, 9), (-8, 1, 10))) is None


def test_stationary_inside_outside_and_tangent():
    sweep = motion((0, 0, 0), (0, 0, 0))
    section = sweep.sections()[0]
    assert sweep.contact_interval(section, box((1, -1, 1), (2, 1, 2))) == (0, 1)
    assert sweep.contact_interval(section, box((0.8, 0.8, 1), (1, 1, 2))) is None
    assert sweep.contact_interval(section, box((-1, -1, 3), (1, 1, 4))) is None
    tangent = motion((-5, 0, 0), (5, 0, 0))
    assert tangent.contact_interval(section, box((0, 1, 1), (1, 2, 2))) == pytest.approx((0.5, 0.6))


def test_multiple_holder_bands_capture_earliest_section_not_iteration_order():
    sections = (AxialEnvelope("holder", 10, 11, 2), AxialEnvelope("holder", 11, 12, 4))
    sweep = motion((-10, 0, 0), (10, 0, 0), replace(TOOL, noncutting_sections=sections))
    result = CollisionScene((CollisionObstacle("jaw", box((0, -1, 10), (1, 1, 13))),)).check_sweep(sweep)
    contact = next(c for c in result.contacts if c.component == "holder")
    assert contact.first_fraction == pytest.approx(0.3)
    assert contact.first_section == sections[1]
    assert contact.first_tip == Vec3(-4, 0, 0)
    assert not result.qualified


def test_source_ratio_maps_subdivided_piece_and_clearance_prefers_earliest_zero():
    segment = SimulationSegment(
        Vec3(-10, 0, 0), Vec3(10, 0, 0), "1", line=9, source_start_ratio=0.25, source_end_ratio=0.75
    )
    scene = CollisionScene(
        (
            CollisionObstacle("later", box((4, -1, 0), (5, 1, 2))),
            CollisionObstacle("earlier", box((-4, -1, 0), (-3, 1, 2))),
        )
    )
    report = simulate((segment,), {"1": TOOL}, StockVolume(box((20, 20, 0), (21, 21, 1)), 1), scene)
    early = next(c for line, c in report.clearance_details if c.obstacle == "earlier")
    assert early.first_fraction == pytest.approx(0.25)
    assert early.source_ratio == pytest.approx(0.375)
    point = next(p for p in analyze_clearance((segment,), {"1": TOOL}, scene).points if p.component == "cutter")
    assert point.obstacle == "earlier"
    assert point.fraction == pytest.approx(0.25)
    assert point.source_ratio == pytest.approx(0.375)


def test_remaining_stock_selects_earliest_occupied_box_not_storage_order(monkeypatch):
    stock = StockVolume(box((-5, -5, 0), (5, 5, 5)), 1)
    later = box((3, -1, 0), (4, 1, 2))
    early = box((-3, -1, 0), (-2, 1, 2))
    monkeypatch.setattr(stock, "occupied_boxes", lambda *_args, **_kwargs: iter((later, early)))
    sweep = motion((-10, 0, 0), (10, 0, 0))
    contacts = stock.collision_contacts(sweep, cutting=False)
    cutter = next(c for c in contacts if c.component == "cutter")
    assert cutter.obstacle_bounds == early and cutter.first_fraction == pytest.approx(0.3)


def test_tilted_contacts_preserve_unknown_position_and_fail_explicit_localization():
    sweep = SweptTool(Vec3(0, 0, 0), Vec3(0, 1, 0), TOOL, Vec3(1, 0, 0))
    obstacle = box((0.5, 0, 0), (1, 1, 1))
    result = CollisionScene((CollisionObstacle("jaw", obstacle),)).check_sweep(sweep)
    assert result.contacts and all(c.first_fraction is None and c.first_tip is None for c in result.contacts)
    with pytest.raises(ValueError, match="fixed"):
        sweep.contact_interval(sweep.sections()[0], obstacle)


def test_out_of_domain_refused_and_remaining_box_cancellation_preserves_stock(monkeypatch):
    sweep = motion((-10, 0, 0), (10, 0, 0))
    with pytest.raises(ValueError, match="domain"):
        sweep.contact_interval(sweep.sections()[0], box((2e9, 0, 0), (2e9 + 1, 1, 1)))
    stock = StockVolume(box((-5, -5, 0), (5, 5, 5)), 1)
    before = stock.snapshot()

    def interrupted(*_args, **_kwargs):
        yield box((3, -1, 0), (4, 1, 2))
        raise InterruptedError("Occupied box query cancelled")

    monkeypatch.setattr(stock, "occupied_boxes", interrupted)
    with pytest.raises(InterruptedError, match="cancelled"):
        stock.collision_contacts(sweep, cutting=False)
    assert stock.snapshot() == before


def test_random_intervals_contain_exact_pose_oracle_and_reverse_symmetrically():
    rng = random.Random(321)
    for _ in range(150):
        sweep = motion(tuple(rng.uniform(-5, 5) for _ in range(3)), tuple(rng.uniform(-5, 5) for _ in range(3)))
        low = tuple(rng.uniform(-4, 4) for _ in range(3))
        obstacle = box(low, tuple(x + 2 for x in low))
        section = sweep.sections()[0]
        interval = sweep.contact_interval(section, obstacle)
        reverse = SweptTool(sweep.end, sweep.start, TOOL).contact_interval(section, obstacle)
        assert (interval is None) == (reverse is None)
        if interval is not None:
            assert reverse == pytest.approx((1 - interval[1], 1 - interval[0]), abs=1e-10)
        for i in range(101):
            t = i / 100
            tip = sweep.start + (sweep.end - sweep.start).scaled(t)
            radial = sum(
                max(a - p, 0, p - b) ** 2
                for p, a, b in zip(tip.tuple[:2], obstacle.minimum.tuple[:2], obstacle.maximum.tuple[:2])
            )
            actual = (
                radial <= 1
                and tip.z + section.high_mm >= obstacle.minimum.z
                and tip.z + section.low_mm <= obstacle.maximum.z
            )
            predicted = interval is not None and interval[0] - 1e-10 <= t <= interval[1] + 1e-10
            assert actual == predicted
