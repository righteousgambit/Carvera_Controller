import math

import pytest

from carveracontroller.machine.receipt_playback import ReceiptPlayback
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording


def playback(samples, gap_seconds=2):
    record = RunRecording(gap_seconds=gap_seconds)
    for stamp, generation in samples:
        record.capture_status("Idle", {}, stamp, stamp + 1000, generation)
    return ReceiptPlayback(RecordingReplay(record.export_bytes()))


def test_elapsed_receipt_intervals_speed_and_end():
    player = playback([(10, 1), (11, 1), (12, 1)])
    player.play(0, 100, 0.25)
    assert player.advance(103).index == 0
    step = player.advance(104)
    assert step.index == 1 and step.running and not step.missing
    step = player.advance(108)
    assert step.index == 2 and not step.running
    player.play(0, 200, 4)
    assert player.advance(200.25).index == 1
    assert player.advance(200.5).index == 2


def test_missing_interval_withholds_pose_then_stops_at_gap_before_same_time_status():
    player = playback([(10, 1), (11, 1), (16, 1)])
    assert player.kinds == ("status", "status", "gap", "status")
    player.play(1, 100)
    step = player.advance(101)
    assert step.index == 1 and step.missing and step.running
    assert step.reason == "missing_interval"
    step = player.advance(106)
    assert step.index == 2 and step.missing and not step.running and step.reason == "gap"
    player.play(2, 200)
    step = player.advance(200)
    assert step.index == 3 and not step.missing and not step.running


def test_delayed_tick_never_skips_connection_boundaries():
    player = playback([(10, 1), (11, 2), (12, 2), (13, 3), (14, 3)])
    player.play(0, 100)
    step = player.advance(1000)
    assert step.index == 1 and step.reason == "connection_boundary"
    player.play(step.index, 2000)
    step = player.advance(3000)
    assert step.index == 4 and step.reason == "connection_boundary"
    player.play(step.index, 4000)
    step = player.advance(5000)
    assert step.index == 6 and not step.running and not step.missing


def test_no_interpolation_and_no_regression_for_duplicate_status_times():
    player = playback([(10, 1), (10, 1), (11, 1)])
    player.play(0, 100)
    assert player.advance(100).index == 1
    assert player.advance(100.5).index == 1
    player.pause()
    with pytest.raises(ValueError, match="paused"):
        player.advance(101)
    player.play(1, 200)
    with pytest.raises(ValueError, match="backwards"):
        player.advance(199)
    assert not player.running


def test_invalid_selection_clock_speed_and_empty_record():
    player = playback([(10, 1), (11, 1)])
    for index in (-1, 2, True, 0.5):
        with pytest.raises(ValueError, match="retained event"):
            player.play(index, 100)
    for value in (-1, math.nan, math.inf, True):
        with pytest.raises(ValueError, match="clock"):
            player.play(0, value)
    for speed in (0, 0.1, 5, math.nan, True):
        with pytest.raises(ValueError, match="speed"):
            player.play(0, 100, speed)
    with pytest.raises(ValueError, match="retained event"):
        playback([]).play(0, 100)


def test_large_retained_buffer_catches_up_without_packet_reads():
    player = playback([(10 + i / 10, 1) for i in range(10000)])
    # Playback retains scalar timing/kind metadata, never program or JPEG bytes.
    player.play(0, 100, 4)
    step = player.advance(350)
    assert step.index == 9999 and not step.running
