import errno
import fcntl
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from carveracontroller.machine import evidence_io
from carveracontroller.machine.evidence_io import (
    BoundedJournalWriter,
    append_jsonl,
    decode_json,
    iter_jsonl,
    write_json_atomic,
)


def test_receipt_is_readback_verified_and_validator_has_locked_descriptor(tmp_path):
    path = tmp_path / "journal"
    validated = []

    def validate(fd):
        validated.append((os.fstat(fd).st_size, list(evidence_io.iter_jsonl_fd(fd, max_bytes=1000))))

    first = append_jsonl(path, {"value": 1}, max_bytes=1000, validate_existing=validate)
    second = append_jsonl(path, {"value": 2}, max_bytes=1000, validate_existing=validate)
    assert first["offset"] == 0 and first["durable"] and first["readback"]
    assert second["offset"] == first["bytes"]
    info = path.stat()
    assert second["file_identity"] == [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]
    assert validated == [(0, []), (first["bytes"], [{"value": 1}])]


def test_concurrent_appenders_do_not_interleave_records(tmp_path):
    path = tmp_path / "journal"
    with ThreadPoolExecutor(max_workers=8) as pool:
        receipts = list(
            pool.map(lambda n: append_jsonl(path, {"n": n, "payload": "x" * 300}, max_bytes=100000), range(40))
        )
    records = list(iter_jsonl(path, max_bytes=100000))
    assert len(receipts) == len(records) == 40
    assert sorted(record["n"] for record in records) == list(range(40))
    assert len({receipt["offset"] for receipt in receipts}) == 40


@pytest.mark.parametrize("data", [b'{"x":1,"x":2}\n', b'{"x":NaN}\n', b'{"x":1e999}\n', b'{"x":"\xff"}\n', b"[]\n"])
def test_untrusted_json_is_rejected(tmp_path, data):
    path = tmp_path / "journal"
    path.write_bytes(data)
    with pytest.raises(ValueError):
        list(iter_jsonl(path, max_bytes=1000))


def test_depth_limit_and_key_types_reject_before_creating_file(tmp_path):
    nested = {}
    for _ in range(66):
        nested = {"x": nested}
    path = tmp_path / "journal"
    with pytest.raises(ValueError):
        append_jsonl(path, nested, max_bytes=10000)
    with pytest.raises(ValueError):
        append_jsonl(path, {1: "invalid"}, max_bytes=10000)
    assert not path.exists()


def test_partial_write_is_preserved_and_blocks_future_append(tmp_path, monkeypatch):
    path = tmp_path / "journal"
    original = os.write
    writes = []

    def fail_after_prefix(fd, data):
        if writes:
            raise OSError(errno.ENOSPC, "disk full")
        writes.append(True)
        return original(fd, data[:3])

    monkeypatch.setattr(os, "write", fail_after_prefix)
    with pytest.raises(OSError, match="disk full"):
        append_jsonl(path, {"n": 1}, max_bytes=1000)
    assert path.read_bytes() == b'{"n'
    monkeypatch.setattr(os, "write", original)
    with pytest.raises(ValueError, match="incomplete"):
        append_jsonl(path, {"n": 2}, max_bytes=1000)
    assert path.read_bytes() == b'{"n'


def test_short_writes_complete_and_no_progress_fails(tmp_path, monkeypatch):
    original = os.write
    monkeypatch.setattr(os, "write", lambda fd, data: original(fd, data[:2]))
    append_jsonl(tmp_path / "short", {"n": 1}, max_bytes=1000)
    assert list(iter_jsonl(tmp_path / "short", max_bytes=1000)) == [{"n": 1}]
    monkeypatch.setattr(os, "write", lambda fd, data: 0)
    with pytest.raises(OSError, match="no progress"):
        append_jsonl(tmp_path / "stalled", {"n": 1}, max_bytes=1000)


def test_readback_failure_is_not_a_durable_receipt(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "pread", lambda *args: b"wrong")
    with pytest.raises(OSError, match="readback"):
        append_jsonl(tmp_path / "journal", {"n": 1}, max_bytes=1000)


@pytest.mark.parametrize("kind", ["symlink", "hardlink", "directory", "fifo"])
def test_unsafe_append_targets_are_rejected_without_changing_original(tmp_path, kind):
    original = tmp_path / "original"
    original.write_bytes(b"original\n")
    path = tmp_path / "journal"
    if kind == "symlink":
        path.symlink_to(original)
    elif kind == "hardlink":
        os.link(original, path)
    elif kind == "directory":
        path.mkdir()
    else:
        os.mkfifo(path)
    with pytest.raises((ValueError, OSError)):
        append_jsonl(path, {"n": 1}, max_bytes=1000)
    assert original.read_bytes() == b"original\n"


def test_os_lock_has_bounded_wait_and_releases_after_holder_closes(tmp_path):
    path = tmp_path / "journal"
    path.write_bytes(b"")
    fd = os.open(path, os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX)
    try:
        with pytest.raises(OSError, match="busy"):
            append_jsonl(path, {"n": 1}, max_bytes=1000, lock_timeout_s=0.01)
    finally:
        os.close(fd)
    append_jsonl(path, {"n": 1}, max_bytes=1000)


def test_limits_apply_to_actual_bytes_lines_and_records(tmp_path):
    path = tmp_path / "journal"
    path.write_bytes(b'{"n":1}\n{"n":2}\n')
    for limits in ({"max_bytes": 8}, {"max_bytes": 100, "max_line_bytes": 7}, {"max_bytes": 100, "max_records": 1}):
        with pytest.raises(ValueError):
            list(iter_jsonl(path, **limits))
    path.write_bytes(b'{"n":1}')
    with pytest.raises(ValueError, match="incomplete"):
        list(iter_jsonl(path, max_bytes=100))
    assert list(iter_jsonl(path, max_bytes=100, strict_tail=False)) == [{"n": 1}]


def test_failed_atomic_export_preserves_destination_and_staging(tmp_path, monkeypatch):
    path = tmp_path / "export.json"
    path.write_bytes(b"old")
    monkeypatch.setattr(os, "write", lambda *args: 0)
    with pytest.raises(OSError):
        write_json_atomic(path, {"new": True})
    assert path.read_bytes() == b"old"
    assert len(list(tmp_path.glob(".export.json.pending-*"))) == 1


def test_atomic_export_has_readback_receipt(tmp_path):
    path = tmp_path / "export.json"
    receipt = write_json_atomic(path, {"n": 1})
    assert receipt["durable"] and receipt["readback"]
    assert decode_json(path.read_bytes()) == {"n": 1}


def test_async_queue_bound_includes_inflight_and_reports_durable_separately(tmp_path, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = append_jsonl

    def blocked(*args, **kwargs):
        entered.set()
        assert release.wait(2)
        return original(*args, **kwargs)

    monkeypatch.setattr(evidence_io, "append_jsonl", blocked)
    writer = BoundedJournalWriter(tmp_path / "journal", max_bytes=1000, max_pending_records=2)
    assert writer.submit({"n": 1})
    assert entered.wait(1)
    try:
        assert writer.submit({"n": 2})
        assert not writer.submit({"n": 3})
        assert not writer.flush(0.01)
        assert writer.status()["durable"] == 0
        assert writer.status()["pending_records"] == 2
    finally:
        release.set()
        assert writer.close(2)
    assert writer.status()["durable"] == 2
    assert writer.status()["dropped"] == 1
    assert not writer.submit({"n": 4})


def test_async_disk_failure_stops_admission_and_retains_pending(tmp_path, monkeypatch):
    def failure(*args, **kwargs):
        raise OSError(errno.ENOSPC, "disk full")

    monkeypatch.setattr(evidence_io, "append_jsonl", failure)
    writer = BoundedJournalWriter(tmp_path / "journal", max_bytes=1000)
    assert writer.submit({"n": 1})
    assert not writer.flush(2)
    assert writer.status()["pending_records"] == 1
    assert writer.status()["durable"] == 0 and "disk full" in writer.status()["error"]
    assert not writer.submit({"n": 2})
    assert not writer.close()


def test_large_line_reader_is_incremental_and_bounded(tmp_path):
    path = tmp_path / "journal"
    data = {"raw": "x" * (2 * 1024 * 1024)}
    append_jsonl(path, data, max_bytes=4 * 1024 * 1024, max_line_bytes=3 * 1024 * 1024)
    assert list(iter_jsonl(path, max_bytes=4 * 1024 * 1024, max_line_bytes=3 * 1024 * 1024)) == [data]


def test_platform_without_positional_io_fails_explicitly_before_mutation(tmp_path, monkeypatch):
    monkeypatch.delattr(os, "pread")
    path = tmp_path / "journal"
    with pytest.raises(OSError, match="unavailable"):
        append_jsonl(path, {"n": 1}, max_bytes=1000)
    with pytest.raises(OSError, match="unavailable"):
        write_json_atomic(path, {"n": 1})
    assert not path.exists()


def test_failed_worker_retains_forensic_records_as_copies(tmp_path, monkeypatch):
    def failure(*args, **kwargs):
        raise RuntimeError("unexpected storage failure")

    monkeypatch.setattr(evidence_io, "append_jsonl", failure)
    writer = BoundedJournalWriter(tmp_path / "journal", max_bytes=1000)
    assert writer.submit({"n": [1]})
    assert not writer.flush(2)
    copies = writer.pending_records()
    assert copies == [{"n": [1]}]
    copies[0]["n"].append(2)
    assert writer.pending_records() == [{"n": [1]}]
    assert "RuntimeError" in writer.status()["error"]
    assert not writer.close()


def test_rejected_oversized_submission_does_not_disable_valid_future_records(tmp_path):
    writer = BoundedJournalWriter(tmp_path / "journal", max_bytes=1000, max_line_bytes=20)
    assert not writer.submit({"large": "x" * 100})
    assert writer.status()["last_submission_error"] and writer.status()["error"] is None
    assert writer.submit({"n": 1})
    assert writer.close(2)
    assert writer.status()["durable"] == 1 and writer.status()["dropped"] == 1
