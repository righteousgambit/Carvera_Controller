"""Read-only snapshot camera client. Independent of the CNC transport and Kivy."""

from __future__ import annotations

import errno
import io
import logging
import math
import socket
import ssl
import threading
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from PIL import Image

DEFAULT_CAMERA_URL = "http://127.0.0.1:18091/snapshot.jpg"
MAX_FRAME_BYTES = 8 * 1024 * 1024
logger = logging.getLogger(__name__)


def validate_camera_url(value):
    value = value.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Use an HTTP or HTTPS snapshot URL without embedded credentials.")
    if parsed.fragment:
        raise ValueError("A snapshot URL cannot contain a fragment.")
    return value


def camera_failure_message(exc, url):
    """Actionable transport diagnostics without exception text or request details."""
    if isinstance(exc, HTTPError):
        if exc.code in (401, 403):
            return "Camera access denied • check camera service authentication."
        if exc.code == 404:
            return "Camera snapshot not found • check the snapshot path in the machine profile."
        if exc.code >= 500:
            return "Camera service error • check the Ubuntu capture service."
        return "Camera HTTP request failed • check the snapshot service."
    reason = exc.reason if isinstance(exc, URLError) else exc
    if isinstance(reason, ssl.SSLError):
        return "Camera TLS verification failed • check the service certificate."
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "Camera request timed out • check host reachability and the capture service."
    if isinstance(reason, socket.gaierror):
        return "Camera host could not be resolved • check the hostname in the machine profile."
    if isinstance(reason, ConnectionRefusedError) or getattr(reason, "errno", None) == errno.ECONNREFUSED:
        host = urlsplit(url).hostname
        if host in ("localhost", "127.0.0.1", "::1"):
            return "Camera connection refused • restore the local camera forward or start its service."
        return "Camera connection refused • check the host port and snapshot service."
    # Only validation messages produced by our decoder are safe to display.
    if isinstance(exc, ValueError) and str(exc) in {
        "The camera endpoint did not return a JPEG snapshot.",
        "Camera frame exceeds the size limit.",
        "Camera capture timestamp is invalid.",
        "Camera returned an unsupported image.",
    }:
        return str(exc)
    return "Camera unavailable • check the Ubuntu service and forward."


@dataclass(frozen=True)
class CameraFrame:
    size: tuple
    pixels: bytes
    captured_at: float | None
    received_at: float
    sequence: int
    jpeg: bytes = b""

    def age(self, wall_now=None, monotonic_now=None):
        if self.captured_at is None:
            return None
        wall_now = time.time() if wall_now is None else wall_now
        monotonic_now = time.monotonic() if monotonic_now is None else monotonic_now
        return max(0, wall_now - self.captured_at, monotonic_now - self.received_at)


def fetch_frame(url, sequence, opener=urlopen):
    request = Request(url, headers={"Cache-Control": "no-cache", "Accept": "image/jpeg"})
    with opener(request, timeout=2) as response:
        if response.headers.get_content_type() != "image/jpeg":
            raise ValueError("The camera endpoint did not return a JPEG snapshot.")
        data = response.read(MAX_FRAME_BYTES + 1)
        if len(data) > MAX_FRAME_BYTES:
            raise ValueError("Camera frame exceeds the size limit.")
        stamp = response.headers.get("X-Camera-Frame-Time")
        captured = float(stamp) if stamp else None
        if captured is not None and (not math.isfinite(captured) or captured > time.time() + 2):
            raise ValueError("Camera capture timestamp is invalid.")
    with Image.open(io.BytesIO(data)) as image:
        if image.format != "JPEG" or image.width > 4096 or image.height > 4096:
            raise ValueError("Camera returned an unsupported image.")
        rgb = image.convert("RGB")
        return CameraFrame(rgb.size, rgb.tobytes(), captured, time.monotonic(), sequence, data)


class WebcamClient:
    """One bounded worker; only its latest frame is retained (no video queue)."""

    def __init__(self, url=DEFAULT_CAMERA_URL, fetch=fetch_frame, start=True):
        self.url = validate_camera_url(url)
        self.fetch = fetch
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.enabled = True
        self.frame = None
        self.error = "Connecting to Ubuntu camera…"
        self.generation = 0
        self.sequence = 0
        self.thread = None
        self.frame_observer = None
        if start:
            self.thread = threading.Thread(target=self._run, name="ubuntu-webcam", daemon=True)
            self.thread.start()

    def configure(self, url):
        url = validate_camera_url(url)
        with self.lock:
            self.url = url
            self.generation += 1
            self.frame = None
            self.error = "Connecting to Ubuntu camera…"
            self.enabled = True

    def set_enabled(self, value):
        with self.lock:
            self.enabled = bool(value)
            self.generation += 1

    def snapshot(self):
        with self.lock:
            return self.enabled, self.frame, self.error

    def set_frame_observer(self, observer):
        """One recording sink; called outside the camera lock after acceptance.

        The sink should enqueue quickly. It receives source generation and both
        server-reported capture time and local receipt time through CameraFrame.
        No extra GET or CNC request is made for recording.
        """
        if observer is not None and not callable(observer):
            raise ValueError("Camera frame observer must be callable")
        with self.lock:
            self.frame_observer = observer

    def poll_once(self):
        with self.lock:
            url, generation, enabled = self.url, self.generation, self.enabled
            self.sequence += 1
            sequence = self.sequence
        if not enabled:
            return
        try:
            frame = self.fetch(url, sequence)
            error = ""
        except Exception as exc:
            # Do not echo request URLs, query strings or credential details.
            frame = None
            error = camera_failure_message(exc, url)
        with self.lock:
            if self.generation != generation or not self.enabled:
                return
            if frame is not None:
                self.frame = frame
            self.error = error
            observer = self.frame_observer if frame is not None else None
        if observer is not None:
            try:
                observer(frame, generation)
            except Exception:
                # Recording must not suppress live viewing or leak sink details.
                logger.warning("Camera recording observer failed; live viewing continues")

    def _run(self):
        while not self.stop_event.is_set():
            self.poll_once()
            self.stop_event.wait(0.5)

    def stop(self):
        self.stop_event.set()
