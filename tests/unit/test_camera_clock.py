import copy
import hashlib
import json
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest

from carveracontroller.machine.camera_calibration_file import CalibrationReference
from carveracontroller.machine.camera_clock import (
    CameraClockExchange,
    camera_clock_headers,
    camera_timing_notice,
)
from carveracontroller.machine.camera_run import (
    CameraRunReplay,
    CameraRunWriter,
    export_camera_bundle,
    import_camera_bundle,
)
from carveracontroller.machine.webcam import CameraFrame, WebcamClient, camera_frame_notice, fetch_frame
from tests.unit.test_camera_calibration_file import reference
from tests.unit.test_webcam import jpeg


def exchange():
    return CameraClockExchange(uuid4().hex, "a" * 64, "b" * 64, 10, 10.2, 1000, 1000.2, 1120.03, 1120.05, 0.001, 0.002)


@contextmanager
def origin(shift=120, mutation=None):
    clock_id = str(uuid4())
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            received = time.time() + shift
            request_id = self.headers.get("X-Camera-Request-ID")
            requests.append((self.command, request_id))
            headers = camera_clock_headers(request_id, received, clock_id, time.time() + shift, 0.001, 0.002)
            if mutation is not None:
                mutation(headers)
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("X-Camera-Frame-Time", repr(time.time() + shift - 0.2))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(jpeg())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/snapshot.jpg?private=not-exported", requests
    finally:
        server.shutdown()
        server.server_close()
        worker.join(2)
        assert not worker.is_alive()


def test_asymmetric_path_bounds_include_true_offset_and_frame_time_without_symmetric_link_assumption():
    sample = exchange()
    low, high = sample.offset_bounds
    assert low < 120 < high and high - low > 0.17
    start, end = sample.frame_bounds(1119.8)
    assert start < 9.8 < end
    assert sample == CameraClockExchange.from_dict(sample.to_dict())
    assert "100 ppm" in camera_timing_notice(sample, 1119.8)
    assert "unqualified" in camera_timing_notice(sample, 1119.8)
    with pytest.raises(ValueError, match="horizon"):
        sample.frame_bounds(1000)
    missing = replace(sample, frame_precision_seconds=None)
    with pytest.raises(ValueError, match="precision is unavailable"):
        missing.frame_bounds(1119.8)
    assert "precision is unavailable" in camera_timing_notice(missing, 1119.8)


@pytest.mark.parametrize(
    "field", ["sent_utc", "received_monotonic", "server_received_utc", "precision_seconds", "frame_precision_seconds"]
)
@pytest.mark.parametrize("value", [True, "10", float("nan"), float("inf"), 10**400, -1])
def test_clock_evidence_never_coerces_numeric_fields(field, value):
    data = exchange().to_dict()
    data[field] = value
    with pytest.raises(ValueError):
        CameraClockExchange.from_dict(data)


@pytest.mark.parametrize(
    "mutation", ["schema", "request", "source", "clock", "local-step", "server-step", "interval", "too-long"]
)
def test_clock_identity_discontinuity_and_inconsistent_intervals_are_rejected(mutation):
    data = exchange().to_dict()
    if mutation == "schema":
        data["schema"] = True
    elif mutation == "request":
        data["request_id"] = "not a request UUID"
    elif mutation == "source":
        data["source_sha256"] = "private URL"
    elif mutation == "clock":
        data["server_clock_sha256"] = "b" * 63
    elif mutation == "local-step":
        data["received_utc"] += 1
    elif mutation == "server-step":
        data["server_sent_utc"] = data["server_received_utc"] - 1
    elif mutation == "interval":
        data["server_sent_utc"] += 2
    else:
        data["received_monotonic"] += 6
        data["received_utc"] += 6
    with pytest.raises(ValueError):
        CameraClockExchange.from_dict(data)


def test_real_http_exchange_preserves_raw_timestamp_and_corrects_age_across_server_clock_offset():
    with origin() as (url, requests):
        frame = fetch_frame(url, 1)
        assert requests == [("GET", frame.clock.request_id)]
        assert frame.clock.source_sha256 == hashlib.sha256(url.encode()).hexdigest()
        assert frame.captured_at > time.time() + 100
        low, high = frame.clock.offset_bounds
        assert low < 120 < high
        assert 0.19 < frame.age(wall_now=time.time() + 3600) < 1
        assert frame.jpeg == jpeg()
        assert "private" not in json.dumps(frame.clock.to_dict())


@pytest.mark.parametrize("mutation", ["nonce", "missing", "nonfinite", "clock"])
def test_incomplete_or_replayed_http_timing_is_a_visible_gap_without_losing_valid_local_time_image(mutation):
    def change(headers):
        if mutation == "nonce":
            headers["X-Camera-Request-ID"] = uuid4().hex
        elif mutation == "missing":
            del headers["X-Camera-Response-Sent"]
        elif mutation == "nonfinite":
            headers["X-Camera-Request-Received"] = "nan"
        else:
            headers["X-Camera-Clock-ID"] = "private URL details"

    with origin(shift=0, mutation=change) as (url, _requests):
        frame = fetch_frame(url, 1)
        assert frame.clock is None and frame.jpeg == jpeg()
        assert "rejected" in frame.clock_gap
        assert "private" not in frame.clock_gap
        assert "receipt-time" in camera_timing_notice(frame.clock, frame.captured_at)


@pytest.mark.parametrize("basis", [None, "jpeg-assembled", "sensor-exposure"])
def test_exact_clock_evidence_survives_reference_camera_manifest_and_portable_bundle(tmp_path, basis):
    def basis_header(headers):
        if basis is not None:
            headers["X-Camera-Frame-Time-Basis"] = basis

    with origin(mutation=basis_header) as (url, _requests):
        frame = fetch_frame(url, 1)
    assert frame.clock.frame_time_basis == basis
    base = reference()
    captured = replace(base, frame=frame, source_sha256=frame.clock.source_sha256)
    decoded = CalibrationReference.from_dict(captured.to_dict())
    assert decoded.frame.clock == frame.clock and decoded.frame.captured_at == frame.captured_at
    broken = copy.deepcopy(captured.to_dict())
    broken["clock"]["source_sha256"] = "c" * 64
    with pytest.raises(ValueError, match="source or receipt"):
        CalibrationReference.from_dict(broken)
    session = str(uuid4())
    writer = CameraRunWriter(tmp_path / "recording", session)
    try:
        assert writer.submit(frame, 0)
    finally:
        writer.close()
    replay = CameraRunReplay(writer.folder)
    assert replay.header["schema"] == 2
    assert CameraClockExchange.from_dict(replay.frames[0]["clock"]) == frame.clock
    bundle = tmp_path / "camera.cvcamera"
    export_camera_bundle(replay, bundle)
    restored = import_camera_bundle(bundle, tmp_path / "imported", session)
    assert restored.frames == replay.frames
    assert restored.read_frame(restored.frames[0]) == frame.jpeg


def test_server_clock_epoch_change_does_not_compare_incompatible_raw_timestamps():
    base = reference().frame
    first = replace(base, captured_at=1120, received_at=10.3, clock=exchange())
    second = replace(first, captured_at=1019, clock=replace(first.clock, server_clock_sha256="c" * 64))
    frames = iter((first, second))
    client = WebcamClient(start=False, fetch=lambda _url, _seq: next(frames))
    client.poll_once()
    client.poll_once()
    assert client.frame.captured_at == 1019 and not client.error
    assert "clock identity changed" in client.frame.clock_gap.lower()


def test_unknown_frame_precision_is_a_gap_and_large_epoch_rounding_is_rejected():
    base = reference().frame
    sample = replace(exchange(), frame_precision_seconds=None)
    frame = replace(base, captured_at=1120, received_at=10.3, clock=sample)
    assert frame.age(wall_now=1000, monotonic_now=10.5) is None
    assert "frame time unknown" in camera_frame_notice(True, frame, "", monotonic_now=10.5)
    with pytest.raises(ValueError, match="resolution"):
        replace(exchange(), server_received_utc=1e30, server_sent_utc=1e30)


def test_clock_epoch_boundaries_refuse_cross_epoch_camera_association_and_legacy_manifest_remains_readable(tmp_path):
    sample = exchange()
    writer = CameraRunWriter(tmp_path, str(uuid4()))
    first = CameraFrame((4, 3), b"", 1119.8, 10.3, 1, jpeg(), clock=sample)
    second = replace(first, received_at=11.3, sequence=2, clock=replace(sample, server_clock_sha256="c" * 64))
    try:
        assert writer.submit(first, 0)
        assert writer.submit(second, 0)
    finally:
        writer.close()
    replay = CameraRunReplay(writer.folder)
    assert replay.at(10.3)["frame"] is not None
    assert replay.at(10.5)["frame"] is None
    assert "boundary" in replay.at(10.5)["reason"]
    # Re-encode the same actual JPEG custody as an original schema-1 manifest,
    # preserving its chain. This verifies reading old archives independently.
    manifest = writer.folder / "frames.jsonl"
    values = [json.loads(line) for line in manifest.read_text().splitlines()]
    values[0]["schema"] = 1
    chain = "0" * 64
    lines = []
    for record in values:
        del record["chain_sha256"]
        record.pop("clock", None)
        raw = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        chain = hashlib.sha256(chain.encode() + raw).hexdigest()
        record["chain_sha256"] = chain
        lines.append(json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False))
    manifest.write_text("\n".join(lines) + "\n")
    legacy = CameraRunReplay(writer.folder)
    assert legacy.header["schema"] == 1
    assert legacy.at(10.5)["frame"] is not None
    assert legacy.read_frame(legacy.frames[0]) == jpeg()
