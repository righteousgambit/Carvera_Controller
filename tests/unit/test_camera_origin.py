import hashlib
import math
from dataclasses import replace
from uuid import uuid4

import pytest

from carveracontroller.machine.camera_clock import CameraClockExchange, camera_timing_notice, read_camera_clock
from carveracontroller.machine.camera_origin import CameraOriginClock
from carveracontroller.machine.camera_origin_patch import prepare_origin
from tests.unit.test_camera_clock import exchange


def clock():
    state = {"utc": 1120.0, "mono": 20.0}
    source = CameraOriginClock(lambda: state["utc"], lambda: state["mono"], 1e-6)
    return source, state


def test_origin_nonce_bound_timing_marks_jpeg_assembly_and_preserves_clock_codec():
    source, state = clock()
    frame = source.sample()
    nonce = uuid4().hex
    state.update(utc=1120.03, mono=20.03)
    request = source.begin(nonce)
    state.update(utc=1120.05, mono=20.05)
    headers = source.headers(request, frame)
    sample = read_camera_clock(headers, nonce, "a" * 64, 10, 10.2, 1000, 1000.2)
    assert sample.frame_time_basis == "jpeg-assembled"
    assert sample.offset_bounds[0] < 120 < sample.offset_bounds[1]
    assert sample.frame_bounds(frame.utc)[0] < 10 < sample.frame_bounds(frame.utc)[1]
    assert "JPEG assembled after FFmpeg delivery" in camera_timing_notice(sample, frame.utc)
    assert sample == CameraClockExchange.from_dict(sample.to_dict())
    legacy = exchange().to_dict()
    legacy.pop("frame_time_basis")
    assert CameraClockExchange.from_dict(legacy).frame_time_basis is None


@pytest.mark.parametrize("nonce", [None, "", "a" * 31, "a" * 33, "G" * 32, "A" * 32, "private\r\nheader", 123])
def test_bad_or_absent_nonce_never_echoes_input_or_invents_timing(nonce):
    source, _state = clock()
    assert source.begin(nonce) is None
    assert source.headers(None, source.sample()) == {}


@pytest.mark.parametrize("delta", [-120, 120])
def test_service_clock_steps_rotate_epoch_and_withhold_cross_epoch_frame_precision(delta):
    source, state = clock()
    old_frame = source.sample()
    old_request = source.begin(uuid4().hex)
    state.update(utc=1121 + delta, mono=21)
    assert source.headers(old_request, old_frame) == {}
    request = source.begin(uuid4().hex)
    headers = source.headers(request, old_frame)
    assert headers["X-Camera-Clock-ID"] != old_frame.epoch
    assert "X-Camera-Frame-Precision" not in headers
    new_frame = source.sample()
    assert "X-Camera-Frame-Precision" in source.headers(request, new_frame)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 1e300, True, "bad"])
def test_bad_origin_sample_withholds_timing_and_new_epoch_recovers(value):
    source, state = clock()
    frame = source.sample()
    state["utc"] = value
    assert source.sample() is None
    state.update(utc=1121, mono=21)
    recovered = source.sample()
    assert recovered.epoch != frame.epoch


def test_bracket_precision_widens_for_clock_read_scheduling_and_reversed_mono_is_refused():
    values = iter([20.0, 20.1, 21.0, 20.9])
    source = CameraOriginClock(lambda: 1120.0, lambda: next(values), 0.001)
    stamp = source.sample()
    assert stamp.monotonic == pytest.approx(20.05)
    assert stamp.precision >= 0.051
    assert source.sample() is None


@pytest.mark.parametrize("value", [0, -1, math.inf, math.nan, 2, True, "bad"])
def test_unsupported_resolution_is_refused(value):
    with pytest.raises(ValueError, match="resolution"):
        CameraOriginClock(resolution=value)


@pytest.mark.parametrize("basis", ["private source", True, 1, "sensor guessed"])
def test_unrecognized_basis_is_not_reflected_to_ui_or_archives(basis):
    data = exchange().to_dict()
    data["frame_time_basis"] = basis
    with pytest.raises(ValueError, match="basis"):
        CameraClockExchange.from_dict(data)


def test_client_rejects_unusable_monotonic_resolution_and_counts_rounding():
    with pytest.raises(ValueError, match="resolution"):
        replace(exchange(), sent_monotonic=1e300, received_monotonic=1e300)
    assert exchange().uncertainty_seconds >= sum(
        math.ulp(value) for value in (exchange().sent_monotonic, exchange().received_monotonic)
    )


def test_origin_patch_refuses_changed_or_unrecognized_source_before_preparing():
    with pytest.raises(ValueError, match="changed"):
        prepare_origin(b"unreviewed")
    source = b"from pathlib import Path\n"
    with pytest.raises(ValueError, match="structure"):
        prepare_origin(source, hashlib.sha256(source).hexdigest())
