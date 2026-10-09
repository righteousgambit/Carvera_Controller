"""Exact-byte file round trips, cancellation and atomic no-clobber publication."""

import hashlib
import json
from pathlib import Path

import pytest

from carveracontroller.machine.channel_plan_file import commit_plan_file, prepare_plan_file, read_plan_file
from carveracontroller.machine.mill_turn_plan import MAX_BYTES, PlanCancelled, example_record


def declaration():
    return json.dumps(example_record(), indent=2, ensure_ascii=False) + "\n"


def test_exact_admitted_bytes_prepare_commit_readback(tmp_path):
    text = declaration()
    target = tmp_path / "declared.channel-plan.json"
    prepared = prepare_plan_file(target, text)
    assert not target.exists()
    assert prepared.temporary.read_bytes() == text.encode()
    receipt = commit_plan_file(prepared)
    prepared.temporary.unlink()
    loaded = read_plan_file(target)
    assert loaded.text == text and loaded.sha256 == hashlib.sha256(text.encode()).hexdigest()
    assert {key: receipt[key] for key in ("path", "sha256", "bytes")} == {
        "path": str(target),
        "sha256": loaded.sha256,
        "bytes": len(text.encode()),
    }
    assert str(receipt["observed_at"]).endswith("+00:00") and loaded.observed_at.endswith("+00:00")
    assert loaded.review.duration_s == 24.5 and not loaded.review.issues


def test_conflicting_declarations_can_be_retained_without_execution(tmp_path):
    record = example_record()
    record["steps"][3]["resources"] = ["turret-main"]
    path = tmp_path / "conflicts.json"
    path.write_text(json.dumps(record))
    loaded = read_plan_file(path)
    assert loaded.review.issues
    prepared = prepare_plan_file(tmp_path / "retained.json", loaded.text)
    try:
        assert commit_plan_file(prepared)["sha256"] == loaded.sha256
    finally:
        prepared.temporary.unlink()


@pytest.mark.parametrize("raw", [b'{"schema":1,"schema":1}', b"not json", b"\xff", b" " * (MAX_BYTES + 1)])
def test_reject_invalid_and_oversize(tmp_path, raw):
    path = tmp_path / "invalid.json"
    path.write_bytes(raw)
    with pytest.raises(ValueError):
        read_plan_file(path)
    assert path.read_bytes() == raw
    with pytest.raises((ValueError, UnicodeError)):
        prepare_plan_file(tmp_path / "bad-export.json", raw.decode("latin1"))
    assert not list(tmp_path.glob(".carvera-channel-*"))


def test_import_detects_same_size_timestamp_replacement(tmp_path, monkeypatch):
    import carveracontroller.machine.channel_plan_file as module

    path = tmp_path / "changes.json"
    path.write_text(declaration())
    original = module.review_plan
    before = path.stat()

    def change(plan, **kwargs):
        result = original(plan, **kwargs)
        raw = path.read_text().replace("DEMO", "EDIT", 1)
        path.write_text(raw)
        import os

        os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
        return result

    monkeypatch.setattr(module, "review_plan", change)
    with pytest.raises(ValueError, match="changed during review"):
        read_plan_file(path)


def test_cancellation_before_io_and_after_preparation_retains_files(tmp_path, monkeypatch):
    import carveracontroller.machine.channel_plan_file as module

    path = tmp_path / "new.json"
    with pytest.raises(PlanCancelled):
        prepare_plan_file(path, declaration(), cancelled=lambda: True)
    with pytest.raises(PlanCancelled):
        read_plan_file(path, cancelled=lambda: True)
    # Cancellation during prepared-file verification cleans up the temporary.
    original = module._read

    def cancel(path, cancelled):
        raise PlanCancelled("cancel during verification")

    monkeypatch.setattr(module, "_read", cancel)
    with pytest.raises(PlanCancelled):
        prepare_plan_file(path, declaration())
    assert not path.exists() and not list(tmp_path.glob(".carvera-channel-*"))
    monkeypatch.setattr(module, "_read", original)


def test_competing_destination_and_tampered_prepared_file_preserved(tmp_path):
    path = tmp_path / "new.json"
    prepared = prepare_plan_file(path, declaration())
    try:
        path.write_bytes(b"competing owner")
        with pytest.raises(FileExistsError):
            commit_plan_file(prepared)
        assert path.read_bytes() == b"competing owner"
        path.unlink()
        prepared.temporary.write_bytes(b"tampered")
        with pytest.raises(ValueError, match="changed before publication"):
            commit_plan_file(prepared)
        assert not path.exists()
    finally:
        prepared.temporary.unlink()


def test_unsupported_atomic_creation_leaves_no_partial_file(tmp_path, monkeypatch):
    import carveracontroller.machine.channel_plan_file as module

    path = tmp_path / "new.json"
    prepared = prepare_plan_file(path, declaration())

    def fail(*args):
        raise OSError("filesystem cannot link")

    monkeypatch.setattr(module.os, "link", fail)
    try:
        with pytest.raises(OSError, match="cannot link"):
            commit_plan_file(prepared)
        assert not path.exists()
    finally:
        prepared.temporary.unlink()


def test_exact_byte_budget_and_unicode_names_roundtrip(tmp_path):
    record = example_record()
    record["name"] = "Café transfer"
    text = json.dumps(record, ensure_ascii=False)
    text += " " * (MAX_BYTES - len(text.encode("utf-8")))
    prepared = prepare_plan_file(tmp_path / "unicode.json", text)
    try:
        assert commit_plan_file(prepared)["bytes"] == MAX_BYTES
        loaded = read_plan_file(prepared.destination)
        assert loaded.text == text and loaded.review.plan.name == "Café transfer"
    finally:
        prepared.temporary.unlink()
