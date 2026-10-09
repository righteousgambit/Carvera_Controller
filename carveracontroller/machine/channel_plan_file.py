"""Bounded exact-byte channel declaration exchange; no transport or UI dependencies."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .mill_turn_plan import MAX_BYTES, PlanCancelled, Review, load_plan, review_plan


@dataclass(frozen=True)
class PlanFile:
    path: str
    text: str
    sha256: str
    review: Review
    observed_at: str


@dataclass(frozen=True)
class PreparedPlanFile:
    destination: Path
    temporary: Path
    sha256: str
    bytes: int


def _check(cancelled: Callable[[], bool]) -> None:
    if cancelled():
        raise PlanCancelled("Channel-plan file operation cancelled")


def _read(path: Path, cancelled: Callable[[], bool]) -> bytes:
    _check(cancelled)
    raw = bytearray()
    with path.open("rb") as source:
        while True:
            _check(cancelled)
            chunk = source.read(min(65536, MAX_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if len(raw) > MAX_BYTES:
                raise ValueError("Channel plan exceeds 256 KiB")
    _check(cancelled)
    return bytes(raw)


def read_plan_file(path: Path, *, cancelled: Callable[[], bool] = lambda: False) -> PlanFile:
    """Admit and review detached bytes; detect path replacement during the review."""
    raw = _read(path, cancelled)
    text = raw.decode("utf-8")
    plan = load_plan(text)
    review = review_plan(plan, cancelled=cancelled)
    if _read(path, cancelled) != raw:
        raise ValueError("Channel plan changed during review; choose it again")
    _check(cancelled)
    return PlanFile(str(path), text, hashlib.sha256(raw).hexdigest(), review, datetime.now(timezone.utc).isoformat())


def prepare_plan_file(path: Path, text: str, *, cancelled: Callable[[], bool] = lambda: False) -> PreparedPlanFile:
    """Prepare exact admitted bytes on the destination volume without publishing."""
    _check(cancelled)
    raw = text.encode("utf-8")
    load_plan(text)
    _check(cancelled)
    descriptor, name = tempfile.mkstemp(prefix=".carvera-channel-", suffix=".pending", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as output:
            for start in range(0, len(raw), 65536):
                _check(cancelled)
                output.write(raw[start : start + 65536])
            output.flush()
            os.fsync(output.fileno())
        if _read(temporary, cancelled) != raw:
            raise ValueError("Prepared channel plan failed exact-byte verification")
        return PreparedPlanFile(path, temporary, hashlib.sha256(raw).hexdigest(), len(raw))
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def commit_plan_file(prepared: PreparedPlanFile) -> dict[str, object]:
    """Publish a complete new file atomically; never overwrite a competing file.

    The owner grants its final current-draft decision before calling. Cancellation
    is disabled at that decision. Hard-link creation on the same volume prevents
    a check/create race; unsupported filesystems fail without a partial destination.
    Readback is an observation, not a lock against subsequent external changes.
    """
    if hashlib.sha256(_read(prepared.temporary, lambda: False)).hexdigest() != prepared.sha256:
        raise ValueError("Prepared channel plan changed before publication")
    os.link(prepared.temporary, prepared.destination)
    raw = _read(prepared.destination, lambda: False)
    if len(raw) != prepared.bytes or hashlib.sha256(raw).hexdigest() != prepared.sha256:
        raise ValueError("Channel plan was published but destination readback changed; inspect the file")
    return {
        "path": str(prepared.destination),
        "sha256": prepared.sha256,
        "bytes": prepared.bytes,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
