"""Retained source identity and ownership never depend on a staging path read."""

import hashlib
from dataclasses import FrozenInstanceError

import pytest

from carveracontroller.machine import retained_program_source as sources
from carveracontroller.machine.retained_program_source import RetainedProgramSource


def source(text="G21\nG1 X1 F100\n", **changes):
    fields = {
        "local_path": "missing.nc",
        "source_hash": hashlib.sha256(text.encode()).hexdigest(),
        "lines": tuple(text.splitlines(keepends=True)),
        "generation": 3,
    }
    fields.update(changes)
    return RetainedProgramSource(**fields)


def test_retained_text_hash_and_immutable_generation_rebind(tmp_path):
    item = source("(Unicode µ and [markup])\nG21\n", local_path=str(tmp_path / "missing.nc"))
    assert item.text() == "".join(item.lines)
    rebound = item.rebound(10)
    assert rebound.lines is item.lines and rebound.source_hash == item.source_hash
    assert item.generation == 3 and rebound.generation == 10
    assert not (tmp_path / "missing.nc").exists()
    with pytest.raises(FrozenInstanceError):
        item.generation = 5


@pytest.mark.parametrize(
    "local,remote,digest,generation",
    [
        ("other.nc", "", None, 3),
        ("missing.nc", "remote.nc", None, 3),
        ("missing.nc", "", "0" * 64, 3),
        ("missing.nc", "", None, 4),
    ],
)
def test_exact_selection_required(local, remote, digest, generation):
    item = source()
    assert item.matches("missing.nc", "", item.source_hash, 3)
    assert not item.matches(local, remote, digest or item.source_hash, generation)


@pytest.mark.parametrize(
    "changes", [{"generation": -1}, {"generation": True}, {"local_path": ""}, {"source_hash": "bad"}, {"lines": []}]
)
def test_metadata_validation(changes):
    with pytest.raises(ValueError):
        source(**changes)


def test_worker_checks_hash_text_budget_and_cancellation(monkeypatch):
    with pytest.raises(ValueError, match="differs"):
        source(source_hash="0" * 64).text()
    with pytest.raises(ValueError, match="must be text"):
        source(lines=(object(),)).text()
    monkeypatch.setattr(sources, "MAX_PROGRAM_BYTES", 8)
    with pytest.raises(ValueError, match="64 MB"):
        source("µ" * 5).text()
    monkeypatch.setattr(sources, "MAX_PROGRAM_BYTES", 64 * 1024 * 1024)
    calls = 0

    def cancel():
        nonlocal calls
        calls += 1
        return calls == 4

    with pytest.raises(InterruptedError):
        source("(" * 20000).text(cancelled=cancel)
    assert calls == 4
