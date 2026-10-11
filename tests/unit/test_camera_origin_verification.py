from dataclasses import replace

import pytest

from carveracontroller.machine.camera_origin_verification import verify_origin
from carveracontroller.machine.webcam import fetch_frame
from scripts.verify_camera_origin import preserve_receipt
from tests.unit import test_camera_origin_patch as origin_tests

patched_origin = origin_tests.patched_origin


def test_live_protocol_receipt_requires_advancing_frame_timestamps_and_exports_no_url_or_images(
    patched_origin, tmp_path
):
    namespace, base, _patched = patched_origin
    url = base + "/snapshot.jpg"

    def fetch(source, sequence):
        frame = fetch_frame(source, sequence)
        namespace["capture"]()
        return frame

    pauses = []
    report = verify_origin(url, fetch=fetch, pause=pauses.append)
    assert report["protocol_qualified"] and report["gap"] == ""
    assert len(report["samples"]) == 3 and pauses == [0.2, 0.2]
    assert not report["physical_exposure_qualified"] and not report["service_file_identity_qualified"]
    assert "private" not in str(report) and base not in str(report)
    assert all("pixels" not in sample and "jpeg" not in sample for sample in report["samples"])
    output = tmp_path / "receipt.json"
    preserve_receipt(report, output)
    with pytest.raises(FileExistsError):
        preserve_receipt(report, output)
    assert namespace["commands"] == []


@pytest.mark.parametrize(
    "scenario", ["missing", "basis", "source", "stale", "epoch", "nonce", "receipt", "backwards", "repeated"]
)
def test_verifier_refuses_each_unproven_protocol_gate(patched_origin, scenario):
    namespace, base, _patched = patched_origin
    first = None

    def fetch(url, sequence):
        nonlocal first
        frame = fetch_frame(url, sequence)
        if scenario != "repeated":
            namespace["capture"]()
        first = frame if first is None else first
        if scenario == "missing":
            frame = replace(frame, clock=None)
        elif scenario == "basis":
            frame = replace(frame, clock=replace(frame.clock, frame_time_basis=None))
        elif scenario == "source":
            frame = replace(frame, clock=replace(frame.clock, source_sha256="a" * 64))
        elif scenario == "stale":
            frame = replace(frame, captured_at=frame.captured_at - 10)
        elif sequence > 1:
            if scenario == "epoch":
                frame = replace(frame, clock=replace(frame.clock, server_clock_sha256="a" * 64))
            elif scenario == "nonce":
                frame = replace(frame, clock=replace(frame.clock, request_id=first.clock.request_id))
            elif scenario == "receipt":
                frame = replace(frame, received_at=first.received_at)
            elif scenario == "backwards":
                frame = replace(frame, captured_at=first.captured_at - 0.1)
        return frame

    report = verify_origin(base + "/snapshot.jpg", 2, fetch=fetch, pause=lambda _seconds: None)
    assert not report["protocol_qualified"] and report["gap"]
    assert namespace["commands"] == []


def test_request_failure_preserves_an_explicit_safe_gap_without_request_details():
    def failed(_url, _sequence):
        raise OSError("private credentials and endpoint")

    report = verify_origin("http://localhost/snapshot.jpg", fetch=failed)
    assert not report["protocol_qualified"] and report["samples"] == []
    assert "private" not in str(report) and "credentials" not in str(report)


@pytest.mark.parametrize("count,interval", [(True, 0.2), (1, 0.2), (9, 0.2), (3, 0), (3, 1), (3, float("nan"))])
def test_invalid_verification_bounds_refuse_before_requests(count, interval):
    calls = []
    with pytest.raises(ValueError, match="2–8"):
        verify_origin("http://localhost/snapshot.jpg", count, interval, fetch=lambda *args: calls.append(args))
    assert calls == []


def test_nonfinite_receipt_refuses_before_file_allocation(tmp_path):
    output = tmp_path / "receipt.json"
    with pytest.raises(ValueError):
        preserve_receipt({"bad": float("nan")}, output)
    assert not output.exists()
