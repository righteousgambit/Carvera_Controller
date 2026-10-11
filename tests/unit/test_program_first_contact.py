"""Analytic entry, initial containment, missing solids, budgets and legacy prefixes."""

from dataclasses import replace
from fractions import Fraction as F

import pytest

from carveracontroller.addons.manufacturing_simulation import SimulationSegment, Vec3
from carveracontroller.addons.manufacturing_simulation.geometry import AxialEnvelope
from carveracontroller.addons.manufacturing_simulation.stock_solid import SolidBudget
from carveracontroller.machine.joint_clearance import bodies_from_record, body_transform
from carveracontroller.machine.kinematic_review import machine_from_record
from carveracontroller.machine.program_first_contact import locate_first_contacts
from carveracontroller.machine.program_surface_clearance import ProgramRotatingResult, ProgramSurfaceClearance
from carveracontroller.machine.rotating_pair import review_rotating_pair
from carveracontroller.machine.rotating_shape import RotatingShape
from carveracontroller.machine.rotating_surface import triangle_contact
from carveracontroller.machine.surface_motion import SurfaceBudget, SurfaceMesh
from tests.unit.test_stock_allowance import example
from tests.unit.test_stock_solid import box


def scene(tmp_path, *, containment=False, opened=False, reversed_faces=False):
    parent, _ = example(tmp_path)
    record = parent.body_review.records[2]
    machine = machine_from_record(record)
    bodies, _ = bodies_from_record(record, machine)
    origin = body_transform(
        machine, next(b for b in bodies if b.name == "T2 cutter"), dict.fromkeys(("X", "Y", "Z"), 0.0)
    ).translation.tuple
    lo = (-10, -10, -10) if containment else (0.25, -2, -0.5)
    hi = (10, 10, 10) if containment else (0.5, 2, 1.5)
    lo, hi = tuple(a + b for a, b in zip(lo, origin)), tuple(a + b for a, b in zip(hi, origin))
    record["collision_bodies"].append(
        {"name": "Obstacle", "frame": "world", "joint_count": 0, "minimum_mm": lo, "maximum_mm": hi}
    )
    triangles = box(lo, hi)
    if opened:
        triangles = triangles[:-1]
    if reversed_faces:
        triangles = tuple(reversed(triangles))
    mesh = SurfaceMesh.create(triangles)
    section = AxialEnvelope("cutter", 0, 1, 0.5)
    segment = SimulationSegment(
        Vec3(-4, 0, 0), Vec3(4, 0, 0), "2", True, line=1, source_start_ratio=0.25, source_end_ratio=0.75
    )
    shift = (origin[0] - 4, origin[1], origin[2])
    rows = review_rotating_pair(
        (section,),
        shift,
        (8, 0, 0),
        mesh=mesh,
        position_error_mm=1e-6,
        surface_budget=SurfaceBudget(),
        solid_budget=SolidBudget(),
        cache={},
    )
    body = replace(parent.body_review, segments=(segment,))
    return ProgramSurfaceClearance(
        body,
        {2: {"Obstacle": mesh}},
        (),
        (),
        1,
        0,
        0,
        len(triangles),
        rotating=tuple(
            ProgramRotatingResult(0, 1, 2, "T2 cutter", "Obstacle", r, F(1, 4) + F(1, 2) * r.sample) for r in rows
        ),
        rotating_envelopes={2: {"T2 cutter": (section,)}},
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_analytic_entry_bracket_all_faces_and_exact_source_ratio(tmp_path, reverse):
    report = scene(tmp_path, reversed_faces=reverse)
    study = locate_first_contacts(report)
    row = study.pairs[0]
    entry = (F(4) + F(1, 4) - F(1, 2) - 2 * F(1e-6)) / 8
    assert row.state == "bounded_contact" and row.earliest_proven
    assert row.lower < entry <= row.upper and row.upper - row.lower <= F(1, 2**20)
    assert row.witness.result.sample == row.upper
    assert row.witness.source_sample_ratio == F(1, 4) + F(1, 2) * row.upper
    assert row.witness.result.witness_triangle is not None and study.prefix_queries > 1


def test_initial_containment_precedes_later_boundary_or_midpoint_witness(tmp_path):
    study = locate_first_contacts(scene(tmp_path, containment=True))
    row = study.pairs[0]
    assert row.state == "initial_overlap" and row.lower == row.upper == 0 and row.earliest_proven
    assert row.witness.result.state == "contained" and row.witness.result.sample == 0


def test_open_solid_with_later_surface_contact_cannot_prove_earliest_volume_contact(tmp_path):
    report = scene(tmp_path, opened=True)
    assert report.rotating[0].result.state == "possible_contact"
    row = locate_first_contacts(report).pairs[0]
    assert row.state == "unavailable" and not row.earliest_proven and row.lower is None
    assert row.witness is report.rotating[0]


def test_earlier_unknown_move_keeps_later_bracket_but_never_claims_earliest(tmp_path):
    report = scene(tmp_path)
    positive = report.rotating[0]
    unknown = replace(positive, result=replace(positive.result, state="unavailable"))
    later = replace(positive, segment_index=1)
    report = replace(
        report,
        body_review=replace(report.body_review, segments=report.body_review.segments * 2),
        rotating=(later, unknown),
    )
    row = locate_first_contacts(report).pairs[0]
    assert row.segment_index == 1 and row.state == "bounded_contact" and not row.earliest_proven
    assert "Earlier" in row.reason


def test_shared_caps_cancel_and_callbacks_restored_without_partial_result(tmp_path):
    report = scene(tmp_path)
    surface, solid = SurfaceBudget(max_pairs=1), SolidBudget()
    callbacks = surface.cancelled, solid.cancelled
    with pytest.raises(ValueError, match="budget"):
        locate_first_contacts(report, surface_budget=surface, solid_budget=solid)
    assert (surface.cancelled, solid.cancelled) == callbacks
    cancelled = [False]

    def progress(*_):
        cancelled[0] = True

    with pytest.raises(InterruptedError):
        locate_first_contacts(
            report, cancelled=lambda: cancelled[0], progress=progress, surface_budget=surface, solid_budget=solid
        )
    assert (surface.cancelled, solid.cancelled) == callbacks
    for precision in (0, 31, True):
        with pytest.raises(ValueError, match="precision"):
            locate_first_contacts(report, resolution_bits=precision)


@pytest.mark.parametrize(
    "section",
    [
        AxialEnvelope("cutter", 0, 2, 1),
        RotatingShape("cutter", 0, 2, 1, primitive="sphere", center_mm=1),
        RotatingShape("cutter", 0, 2, 1, primitive="cone"),
    ],
)
def test_prefix_is_continuous_exact_and_preserves_unscaled_original_delta(section):
    triangle = ((0, 0, 1),) * 3
    # Cylinder/sphere enter at 3/8; cone radius at z=1 is .5, entry 7/16.
    entry = F(7, 16) if isinstance(section, RotatingShape) and section.primitive == "cone" else F(3, 8)
    assert triangle_contact(section, triangle, (-4, 0, 0), (8, 0, 0), upper_time=entry - F(1, 2**30)) is None
    hit = triangle_contact(section, triangle, (-4, 0, 0), (8, 0, 0), upper_time=entry)
    assert hit is not None and hit.sample == entry
    assert triangle_contact(section, triangle, (-4, 0, 0), (8, 0, 0), upper_time=F(0)) is None
    with pytest.raises(ValueError, match="exact fraction"):
        triangle_contact(section, triangle, upper_time=0.5)


def test_irrational_ball_entry_has_rational_outward_time_bracket_without_float_root():
    ball = RotatingShape("cutter", 0, 2, 1, primitive="sphere", center_mm=1)
    triangle = ((0, 0, 0.5),) * 3
    lo, hi = F(0), F(1, 2)
    for _ in range(25):
        mid = (lo + hi) / 2
        hit = triangle_contact(ball, triangle, (-4, 0, 0), (8, 0, 0), upper_time=mid)
        if hit is None:
            lo = mid
        else:
            hi = hit.sample
    # Independent sphere section at z=.5 has radius squared3/4. Its entry
    # time contains sqrt(3), which must never be rounded into an exact pose.
    assert (4 - 8 * lo) ** 2 > F(3, 4)
    assert (4 - 8 * hi) ** 2 <= F(3, 4)
    assert hi - lo <= F(1, 2**25)


def test_starting_boundary_is_exact_zero_and_unsorted_pair_rows_do_not_hide_it(tmp_path):
    report = scene(tmp_path)
    row = report.rotating[0]
    report = replace(
        report,
        body_review=replace(
            report.body_review, segments=(replace(report.body_review.segments[0], start=Vec3(0.25, 0, 0)),)
        ),
    )
    first = locate_first_contacts(report).pairs[0]
    assert first.state == "initial_overlap" and first.lower == first.upper == 0
    assert first.witness.result.sample == 0 and first.witness.result.witness_triangle is not None


def test_complete_section_set_can_contact_before_the_retained_candidate_section(tmp_path):
    report = scene(tmp_path)
    original = report.rotating_envelopes[2]["T2 cutter"][0]
    wider = replace(original, radius_mm=0.75)
    report = replace(report, rotating_envelopes={2: {"T2 cutter": (original, wider)}})
    row = locate_first_contacts(report).pairs[0]
    entry = (F(4) + F(1, 4) - F(3, 4) - 2 * F(1e-6)) / 8
    assert row.lower < entry <= row.upper
    assert row.witness.result.section_index == 1
