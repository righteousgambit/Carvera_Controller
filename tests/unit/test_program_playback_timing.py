"""Independent nominal time arithmetic, gaps and exact source/WCS bindings."""

from dataclasses import replace
from fractions import Fraction as F

import pytest

from carveracontroller.machine.program_joint_clearance import ProgramClearanceSource
from carveracontroller.machine.program_operations import ProgramOperations
from carveracontroller.machine.program_playback_timing import PlaybackClock, prepare_program_timing
from tests.unit.test_program_joint_clearance import review


def timed(text, **settings):
    program = ProgramOperations.from_text("G21 G90 G91.1 G17 G94 G54\nT1 M6\nG0 X0 Y0 Z0\n" + text, **settings)
    source = ProgramClearanceSource.capture(program)
    return prepare_program_timing(source, review(program), {"G54": (-180, -120, -110)})


def motions(timing):
    return [s for s in timing.spans if s.move is not None]


def test_units_feed_changes_and_rapid_are_independent_nominal_seconds():
    timing = timed("G1 X10 F100\nG20 G1 X1 F1\nG0 X2", rapid_mm_min=254)
    assert [s.seconds for s in motions(timing)] == pytest.approx([6, 60 * 15.4 / 25.4, 6])
    assert timing.gap_count == 2  # ATC and unresolved first positioning block.
    assert timing.advance(PlaybackClock(), 100).gap.line == 2
    clock = timing.seek(0, F(0))
    frame = timing.advance(clock, 3)
    assert frame.position == F(1, 2) and frame.clock.elapsed_seconds == 3
    assert timing.known_seconds == pytest.approx(sum(s.seconds for s in motions(timing)))


def test_inverse_time_arc_is_one_block_duration_and_missing_block_feed_is_gap():
    timing = timed("G93 G2 X10 Y0 I5 J0 F2\nG1 X11")
    arc = [s for s in motions(timing) if s.line == 4]
    assert len(arc) > 2 and sum(s.seconds for s in arc) == pytest.approx(30)
    assert motions(timing)[-1].seconds is None
    assert "this source block" in motions(timing)[-1].reason


def test_known_dwell_advances_elapsed_without_moving_and_unknown_wait_stops():
    timing = timed("G1 X10 F600\nG4 P2\nM0\nG1 X20", dwell_p_seconds=1)
    result = timing.advance(timing.seek(0, F(0)), 2)
    assert result.position == 1 and result.clock.elapsed_seconds == 2 and result.gap is None
    result = timing.advance(result.clock, 10)
    assert result.position == 1 and result.clock.elapsed_seconds == 3 and result.gap.line == 6
    resumed = timing.advance(PlaybackClock(result.clock.span + 1, F(0), result.clock.elapsed_seconds), 1)
    assert resumed.done and resumed.position == 2 and resumed.clock.elapsed_seconds == 4
    assert timed("G4 P2\nG1 X10 F100").spans[2].seconds is None


def test_g95_missing_rapid_and_zero_length_blocks_do_not_infer_spindle_or_loop():
    timing = timed("G0 X1\nG95 G1 X2 F0.1")
    assert all(s.seconds is None for s in motions(timing))
    assert "spindle" in motions(timing)[-1].reason
    zero = timed("G1 X0 F100\nG1 X1")
    result = zero.advance(zero.seek(0, F(0)), 100)
    assert result.done and result.position == len(zero.body.segments)


def test_timing_refuses_changed_source_datums_nonfinite_rate_and_cancel():
    timing = timed("G1 X10 F100")
    source, body = timing.source, timing.body
    with pytest.raises(ValueError, match="source"):
        prepare_program_timing(replace(source, file_hash="other"), body, {"G54": (-180, -120, -110)})
    with pytest.raises(ValueError, match="datums"):
        prepare_program_timing(source, body, {"G54": (-179, -120, -110)})
    for rate in (True, 0, -1, float("inf"), float("nan"), 1_000_001):
        with pytest.raises(ValueError, match="rapid"):
            prepare_program_timing(source, body, {"G54": (-180, -120, -110)}, rapid_mm_min=rate)
    with pytest.raises(InterruptedError):
        prepare_program_timing(source, body, {"G54": (-180, -120, -110)}, cancelled=lambda: True)


def test_finite_subnormal_feed_cannot_publish_infinite_nominal_duration():
    timing = timed("G1 X10 F0." + "0" * 319 + "1")
    assert motions(timing)[0].seconds is None
    assert "finite timing range" in motions(timing)[0].reason
    assert timing.known_seconds == 0
