"""Bounded atomic retention of explicit local kinematic geometry declarations."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path

from carveracontroller.machine.kinematic_review import machine_from_record


def save_kinematic_profile(path: str | Path, record: object, *, cancelled: Callable[[], bool] = lambda: False) -> str:
    machine_from_record(record)
    data = (json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + "\n").encode("utf-8")
    if len(data) > 65536:
        raise ValueError("Kinematic profile exceeds 64 KiB")
    return retain_geometry_bytes(path, data, cancelled=cancelled)


def retain_geometry_bytes(path: str | Path, data: bytes, *, cancelled: Callable[[], bool] = lambda: False) -> str:
    """Atomically publish already bounded/validated geometry bytes and read back."""
    path = Path(path)
    staging = None
    try:
        if cancelled():
            raise InterruptedError("Geometry save cancelled before publication")
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name + ".", delete=False) as stream:
            staging = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if cancelled():
            raise InterruptedError("Geometry save cancelled before publication")
        os.replace(staging, path)
        if path.read_bytes() != data:
            raise OSError("Saved geometry readback differs from declared bytes")
        return hashlib.sha256(data).hexdigest()
    finally:
        if staging is not None:
            staging.unlink(missing_ok=True)
