import io
import time
from email.message import Message

import pytest
from PIL import Image

from carveracontroller.machine.webcam import CameraFrame, WebcamClient, fetch_frame, validate_camera_url


class Response(io.BytesIO):
    def __init__(self, data, content_type="image/jpeg", timestamp=None):
        super().__init__(data)
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        if timestamp is not None:
            self.headers["X-Camera-Frame-Time"] = str(timestamp)


def jpeg():
    data = io.BytesIO()
    Image.new("RGB", (4, 3), (50, 80, 100)).save(data, format="JPEG")
    return data.getvalue()


def test_valid_jpeg_decoded_and_only_get_used():
    requests = []
    captured = time.time() - 0.3

    def opener(request, timeout):
        requests.append((request.get_method(), timeout))
        return Response(jpeg(), timestamp=captured)

    frame = fetch_frame("http://localhost/snapshot.jpg", 1, opener)
    assert frame.size == (4, 3)
    assert len(frame.pixels) == 36
    assert frame.jpeg == jpeg()
    assert frame.age() >= 0.3
    assert requests == [("GET", 2)]


def test_cached_snapshot_remains_stale():
    frame = fetch_frame(
        "http://localhost/snapshot.jpg", 1, lambda *_args, **_kwargs: Response(jpeg(), timestamp=time.time() - 60)
    )
    assert frame.age() >= 60


def test_missing_capture_timestamp_is_unknown():
    frame = fetch_frame("http://localhost/snapshot.jpg", 1, lambda *_args, **_kwargs: Response(jpeg()))
    assert frame.age() is None


@pytest.mark.parametrize("stamp", ["nan", "inf", "future"])
def test_invalid_timestamp_rejected(stamp):
    # Construct the future case when the test executes, not at collection.
    # A long integration suite must not turn it into a valid past timestamp.
    if stamp == "future":
        stamp = time.time() + 100
    with pytest.raises(ValueError):
        fetch_frame("http://localhost/snapshot.jpg", 1, lambda *_args, **_kwargs: Response(jpeg(), timestamp=stamp))


def test_html_error_not_treated_as_video():
    with pytest.raises(ValueError, match="JPEG"):
        fetch_frame(
            "http://localhost/snapshot.jpg", 1, lambda *_args, **_kwargs: Response(b"error", content_type="text/html")
        )


@pytest.mark.parametrize("url", ["file:///tmp/image.jpg", "http://user:password@host/x", "http://", "ftp://host/x"])
def test_invalid_or_credential_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_camera_url(url)


def test_pause_during_inflight_fetch_cannot_publish_a_frame():
    client = None

    def fetch(_url, sequence):
        client.set_enabled(False)
        return CameraFrame((1, 1), b"abc", time.time(), time.monotonic(), sequence)

    client = WebcamClient(fetch=fetch, start=False)
    client.poll_once()
    assert client.snapshot() == (False, None, "Connecting to Ubuntu camera…")


def test_reconfigured_source_discards_old_inflight_frame():
    client = None

    def fetch(_url, sequence):
        client.configure("http://localhost/new.jpg")
        return CameraFrame((1, 1), b"abc", time.time(), time.monotonic(), sequence)

    client = WebcamClient(fetch=fetch, start=False)
    client.poll_once()
    assert client.frame is None
    assert client.url == "http://localhost/new.jpg"


def test_error_retains_frame_but_no_longer_reports_live():
    client = WebcamClient(
        start=False, fetch=lambda _url, seq: CameraFrame((1, 1), b"abc", time.time(), time.monotonic(), seq)
    )
    client.poll_once()
    original = client.frame

    def failed(_url, _seq):
        raise OSError("secret URL details")

    client.fetch = failed
    client.poll_once()
    assert client.frame is original
    assert "unavailable" in client.error
    assert "secret" not in client.error


def test_recording_sink_receives_exact_accepted_frame_and_generation_outside_lock():
    received = []
    client = WebcamClient(start=False, fetch=lambda _url, seq: CameraFrame((1, 1), b"abc", 1000, 10, seq, b"jpeg"))

    def observe(frame, generation):
        # Taking the lock again proves the callback does not hold it.
        assert client.snapshot()[1] is frame
        received.append((frame.jpeg, frame.captured_at, frame.received_at, generation))

    client.set_frame_observer(observe)
    client.poll_once()
    assert received == [(b"jpeg", 1000, 10, 0)]
    client.set_enabled(False)
    client.poll_once()
    assert len(received) == 1


def test_recording_sink_failure_does_not_suppress_live_frame(caplog):
    client = WebcamClient(start=False, fetch=lambda _url, seq: CameraFrame((1, 1), b"abc", 1000, 10, seq))

    def fail(_frame, _generation):
        raise OSError("private sink details")

    client.set_frame_observer(fail)
    client.poll_once()
    assert client.frame is not None and client.error == ""
    assert "private sink details" not in caplog.text
