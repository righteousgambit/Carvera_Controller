"""Prepare a reviewable, hash-bound patch of the existing Ubuntu JPEG service."""

from __future__ import annotations

import ast
import hashlib

REVIEWED_ORIGIN_SHA256 = "d2508383aa96508cf15b11814de5f097e6eba20bbd8d93ea1fe72b5c18295548"
MAX_ORIGIN_BYTES = 64 * 1024


def prepare_origin(source: bytes, expected_sha256: str = REVIEWED_ORIGIN_SHA256) -> bytes:
    if not isinstance(source, bytes) or len(source) > MAX_ORIGIN_BYTES:
        raise ValueError("Origin source exceeds its bounds")
    if hashlib.sha256(source).hexdigest() != expected_sha256:
        raise ValueError("Origin source changed; review the exact current service before preparing")
    text = source.decode("utf-8")
    old = ast.parse(text)
    edits = (
        ("from pathlib import Path\n", "from pathlib import Path\nfrom camera_origin import CameraOriginClock\n"),
        (
            "condition=threading.Condition()",
            "condition=threading.Condition()\norigin_clock=CameraOriginClock()\nlatest_frame_timing=None",
        ),
        (
            "global latest,last_frame,last_frame_utc,ffmpeg",
            "global latest,last_frame,last_frame_utc,ffmpeg,latest_frame_timing",
        ),
        (
            "latest=frame;last_frame=time.monotonic();last_frame_utc=time.time();condition.notify_all()",
            "latest_frame_timing=origin_clock.sample()\n"
            "                    latest=frame\n"
            "                    if latest_frame_timing is None:\n"
            "                        last_frame=time.monotonic();last_frame_utc=time.time()\n"
            "                    else:\n"
            "                        last_frame=latest_frame_timing.monotonic;last_frame_utc=latest_frame_timing.utc\n"
            "                    condition.notify_all()",
        ),
        (
            "def data(self,code,body,kind='application/json',captured=None):",
            "def data(self,code,body,kind='application/json',captured=None,request_timing=None,frame_timing=None):",
        ),
        (
            "if kind=='image/jpeg': self.send_header('X-Camera-Frame-Time',str(captured))",
            "if kind=='image/jpeg':\n"
            "            self.send_header('X-Camera-Frame-Time',str(captured))\n"
            "            for key,value in origin_clock.headers(request_timing,frame_timing).items():\n"
            "                self.send_header(key,value)",
        ),
        (
            "def do_GET(self):\n",
            "def do_GET(self):\n        request_timing=origin_clock.begin(self.headers.get('X-Camera-Request-ID'))\n",
        ),
        (
            "frame=latest;captured=last_frame_utc",
            "frame=latest;captured=last_frame_utc;frame_timing=latest_frame_timing",
        ),
        (
            "self.data(200,frame,'image/jpeg',captured=captured)",
            "self.data(200,frame,'image/jpeg',captured=captured,request_timing=request_timing,frame_timing=frame_timing)",
        ),
    )
    for before, after in edits:
        if text.count(before) != 1:
            raise ValueError("Origin structure differs from the reviewed snapshot service")
        text = text.replace(before, after)
    new = ast.parse(text)

    # All original top-level definitions/statements except the capture and
    # handler retain their exact semantics, including startup/listeners/page.
    def protected(tree: ast.Module) -> list[str]:
        return [
            ast.dump(node, include_attributes=False)
            for node in tree.body
            if not (isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in ("capture", "Handler"))
        ]

    prior = protected(old)
    current = protected(new)
    if not all(node in current for node in prior):
        raise ValueError("Origin patch changed protected top-level semantics")
    old_handler = next(node for node in old.body if isinstance(node, ast.ClassDef) and node.name == "Handler")
    new_handler = next(node for node in new.body if isinstance(node, ast.ClassDef) and node.name == "Handler")
    for method in old_handler.body:
        if isinstance(method, ast.FunctionDef) and method.name not in ("data", "do_GET"):
            counterpart = next(
                node for node in new_handler.body if isinstance(node, ast.FunctionDef) and node.name == method.name
            )
            if ast.dump(method, include_attributes=False) != ast.dump(counterpart, include_attributes=False):
                raise ValueError("Origin patch changed protected camera controls")
    return text.encode("utf-8")
