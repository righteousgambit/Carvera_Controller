"""Full nominal inputs without clearance claims or relaxed collision budgets."""

from dataclasses import replace

import pytest

from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.program_playback_preparation import prepare_program_playback
from carveracontroller.machine.program_playback_timing import prepare_program_timing
from tests.unit.test_program_stock_evolution import stock_example


def test_nominal_preparation_preserves_all_geometry_motion_stock_and_explicit_unknown_clearance():
    source, offsets, expected, captures = stock_example(ball=True, repeat=True, rotation=31, tilt=(20, -10))
    prepared = prepare_program_playback(source, captures, offsets, stock_resolution_mm=0.5)
    report = prepared.scene
    assert report.body_review.segments == expected.body_review.segments
    assert report.meshes == expected.meshes
    assert report.stock_evolution.steps == expected.stock_evolution.steps
    assert report.stock_evolution.final_snapshots == expected.stock_evolution.final_snapshots
    assert report.body_review.contacts == () and report.contacts == () and report.body_review.tested_pairs == 0
    assert "clearance_not_reviewed" in report.body_review.status
    assert "has not been reviewed" in report.qualification
    assert prepare_program_timing(source, report.body_review, offsets).gap_count >= 2


def test_curve_parameters_bind_nominal_segments_and_do_not_remove_uncertified_curve_material():
    source, offsets, _, captures = stock_example(ball=True)
    program = ProgramOperations.from_text(source.text + "\nG2 X0 Y1 I-0.5 J0.5 F100")
    source = ProgramClearanceSource.capture(program)
    prepared = prepare_program_playback(source, captures, offsets, stock_resolution_mm=0.5)
    curve = source.curve_enclosures[-1]
    segments = [s for s in prepared.scene.body_review.segments if s.line == curve.line_number]
    assert [s.source_start_ratio for s in segments] == list(curve.parameters[:-1])
    assert [s.source_end_ratio for s in segments] == list(curve.parameters[1:])
    assert all(
        s.state == "curve material retained" and s.removed_mm3 == 0
        for s in prepared.scene.stock_evolution.steps
        if s.line == curve.line_number
    )
    prepare_program_timing(source, prepared.scene.body_review, offsets)


def test_nominal_preparation_refuses_unknown_tools_limits_datums_and_cancel():
    source, offsets, _, captures = stock_example()
    with pytest.raises(ValueError, match="profiles"):
        prepare_program_playback(source, {}, offsets)
    with pytest.raises(ValueError, match="datums"):
        prepare_program_playback(replace(source, declared_offsets=(("G54", (0, 0, 0)),)), captures, offsets)
    far = ProgramClearanceSource.capture(ProgramOperations.from_text(source.text + "\nG1 X1000"))
    with pytest.raises(ValueError, match="travel"):
        prepare_program_playback(far, captures, offsets)
    with pytest.raises(InterruptedError):
        prepare_program_playback(source, captures, offsets, cancelled=lambda: True)
