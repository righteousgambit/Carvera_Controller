import hashlib
import json

import pytest

from carveracontroller.machine.kinematic_profile_io import save_kinematic_profile
from carveracontroller.machine.kinematic_review import example_profile, machine_from_record


def test_saved_declaration_reads_back_and_keeps_profile_contract(tmp_path):
    path = tmp_path / "geometry.json"
    record = example_profile("Head / table")
    digest = save_kinematic_profile(path, record)
    assert digest == hashlib.sha256(path.read_bytes()).hexdigest()
    assert json.loads(path.read_bytes()) == record
    machine_from_record(json.loads(path.read_bytes()))
    assert len(list(tmp_path.iterdir())) == 1


def test_cancel_and_failed_replace_preserve_previous_profile_and_remove_staging(tmp_path, monkeypatch):
    import carveracontroller.machine.kinematic_profile_io as module

    path = tmp_path / "geometry.json"
    path.write_bytes(b"previous")
    record = example_profile("Head / table")
    calls = 0

    def cancelled():
        nonlocal calls
        calls += 1
        return calls == 2

    with pytest.raises(InterruptedError):
        save_kinematic_profile(path, record, cancelled=cancelled)
    assert path.read_bytes() == b"previous" and list(tmp_path.iterdir()) == [path]
    monkeypatch.setattr(module.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("replace fault")))
    with pytest.raises(OSError, match="replace fault"):
        save_kinematic_profile(path, record)
    assert path.read_bytes() == b"previous" and list(tmp_path.iterdir()) == [path]


def test_invalid_profile_never_replaces_file(tmp_path):
    path = tmp_path / "geometry.json"
    path.write_bytes(b"previous")
    with pytest.raises(ValueError):
        save_kinematic_profile(path, {"schema": 1, "tool_chain": []})
    assert path.read_bytes() == b"previous"
