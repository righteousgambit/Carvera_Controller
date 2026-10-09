import json
import threading
from types import SimpleNamespace
from uuid import uuid4

import pytest

from carveracontroller.machine.camera_run import CameraRunReplay, CameraRunWriter


def frame(sequence, received, data=b"\xff\xd8payload\xff\xd9"):
    return SimpleNamespace(jpeg=data, size=(1, 1), sequence=sequence, received_at=received, captured_at=None)


def test_camera_writer_preserves_bytes_and_distinguishes_source_boundaries(tmp_path):
    session = str(uuid4())
    writer = CameraRunWriter(tmp_path, session)
    assert writer.submit(frame(1, 10), 0)
    assert writer.submit(frame(2, 11), 0)
    assert writer.submit(frame(3, 14), 1)
    status = writer.close()
    assert status["closed"] and status["written"] == 3 and not writer.thread.is_alive()
    replay = CameraRunReplay(writer.folder)
    assert replay.header["recording_session_id"] == session
    assert replay.read_frame(replay.frames[0]) == frame(1, 10).jpeg
    assert replay.at(10.5)["receipt_age_seconds"] == 0.5
    assert replay.at(12)["frame"] is None
    assert replay.at(9)["frame"] is None and replay.at(15)["frame"] is None
    assert replay.at(14)["frame"]["generation"] == 1
    assert "unqualified" in replay.at(14)["reason"]
    modified = replay.frames[0]
    modified["sha256"] = "../private"
    with pytest.raises(ValueError, match="does not belong"):
        replay.read_frame(modified)
    assert replay.frames[0]["sha256"] != "../private"


def test_camera_writer_queue_loss_is_explicit_without_blocking_capture(tmp_path, monkeypatch):
    gate, started = threading.Event(), threading.Event()
    writer = CameraRunWriter(tmp_path, str(uuid4()), capacity=1)
    original = writer._persist

    def blocked(item, data):
        started.set()
        assert gate.wait(5)
        return original(item, data)

    monkeypatch.setattr(writer, "_persist", blocked)
    assert writer.submit(frame(1, 10), 0)
    assert started.wait(2)
    assert writer.submit(frame(2, 11), 0)
    assert not writer.submit(frame(3, 12), 0)
    gate.set()
    status = writer.close()
    assert status["dropped"] == 1 and status["written"] == 2
    assert CameraRunReplay(writer.folder).footer["dropped"] == 1
    before = writer.status()
    assert not writer.submit(frame(4, 13), 0)
    assert writer.status() == before


def test_camera_writer_limit_and_corrupt_asset_are_reported_and_preserved(tmp_path):
    data = frame(1, 10).jpeg
    writer = CameraRunWriter(tmp_path, str(uuid4()), max_bytes=len(data))
    assert writer.submit(frame(1, 10), 0)
    assert not writer.submit(frame(2, 11), 0)
    status = writer.close()
    assert status["written"] == 1 and "limit" in status["error"]
    replay = CameraRunReplay(writer.folder)
    asset = writer.folder / (replay.frames[0]["sha256"] + ".jpg")
    asset.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="bytes differ"):
        replay.read_frame(replay.frames[0])
    assert asset.read_bytes() == b"corrupt"


def test_camera_manifest_tampering_rejected_before_replay(tmp_path):
    writer = CameraRunWriter(tmp_path, str(uuid4()))
    writer.submit(frame(1, 10), 0)
    writer.close()
    journal = writer.folder / "frames.jsonl"
    records = [json.loads(line) for line in journal.read_bytes().splitlines()]
    records[1]["received_at"] = 99
    journal.write_text("\n".join(json.dumps(record) for record in records) + "\n")
    with pytest.raises(ValueError, match="digest chain"):
        CameraRunReplay(writer.folder)


def test_camera_writer_failure_preserves_partial_session_and_releases_worker(tmp_path, monkeypatch):
    writer = CameraRunWriter(tmp_path, str(uuid4()))

    def fail(_item, _data):
        raise OSError("private path details")

    monkeypatch.setattr(writer, "_persist", fail)
    writer.submit(frame(1, 10), 0)
    status = writer.close()
    assert status["closed"] and status["written"] == 0 and status["dropped"] == 1
    assert "private" not in status["error"]
    replay = CameraRunReplay(writer.folder)
    assert replay.frames == [] and "persistence failed" in replay.footer["error"]


def test_camera_drain_commits_bounded_groups_without_waiting_to_fill(tmp_path, monkeypatch):
    writer = CameraRunWriter(tmp_path, str(uuid4()), capacity=32)
    entered, release = threading.Event(), threading.Event()
    original = writer._commit_batch
    groups = []

    def held_first_batch(batch):
        groups.append(len(batch))
        if len(groups) == 1:
            entered.set()
            assert release.wait(5)
        return original(batch)

    monkeypatch.setattr(writer, "_commit_batch", held_first_batch)
    try:
        assert writer.submit(frame(1, 10), 0)
        assert entered.wait(2)  # An isolated frame is admitted immediately.
        for sequence in range(2, 19):
            assert writer.submit(frame(sequence, sequence + 9), 0)
        writer.request_stop()
        release.set()
        status = writer.close()
        assert groups == [1, 8, 8, 1]
        assert status["written"] == 18 and status["pending_bytes"] == 0 and not status["error"]
        replay = CameraRunReplay(writer.folder)
        assert [receipt["sequence"] for receipt in replay.frames] == list(range(1, 19))
        assert replay.footer["written"] == 18
        assert len(list(writer.folder.glob("*.jpg"))) == 1
        assert all(replay.read_frame(receipt) == frame(1, 10).jpeg for receipt in replay.frames)
    finally:
        release.set()
        writer.close()


def test_camera_written_waits_for_journal_sync_and_timeout_retains_owned_worker(tmp_path, monkeypatch):
    from carveracontroller.machine import camera_run

    writer = CameraRunWriter(tmp_path, str(uuid4()))
    journal_fd = writer._journal.fileno()
    entered, release = threading.Event(), threading.Event()
    original = camera_run.os.fsync

    def held_journal_sync(fd):
        if fd == journal_fd:
            entered.set()
            assert release.wait(5)
        return original(fd)

    monkeypatch.setattr(camera_run.os, "fsync", held_journal_sync)
    try:
        assert writer.submit(frame(1, 10), 0)
        assert entered.wait(2)
        assert writer.status()["written"] == 0
        assert writer.status()["pending_bytes"] == len(frame(1, 10).jpeg)
        worker = writer.thread
        with pytest.raises(TimeoutError, match="retain the existing worker"):
            writer.close(timeout=0.01)
        assert writer.stopping and writer.thread is worker and worker.is_alive()
        assert not writer.status()["closed"] and not writer.submit(frame(2, 11), 0)
        release.set()
        status = writer.close()
        assert status["written"] == 1 and status["closed"] and status["pending_bytes"] == 0
        assert CameraRunReplay(writer.folder).footer["written"] == 1
    finally:
        release.set()
        writer.close()


def test_failed_group_commit_accounts_for_batch_and_queued_frames(tmp_path, monkeypatch):
    writer = CameraRunWriter(tmp_path, str(uuid4()), capacity=32)
    entered, release = threading.Event(), threading.Event()
    original_commit, original_append = writer._commit_batch, writer._append_many
    groups, journal_groups = [], []

    def held_first_batch(batch):
        groups.append(len(batch))
        if len(groups) == 1:
            entered.set()
            assert release.wait(5)
        return original_commit(batch)

    def fail_second_group(values):
        journal_groups.append(len(values))
        if len(journal_groups) == 2:
            raise OSError("private disk path details")
        return original_append(values)

    monkeypatch.setattr(writer, "_commit_batch", held_first_batch)
    monkeypatch.setattr(writer, "_append_many", fail_second_group)
    try:
        assert writer.submit(frame(1, 10), 0)
        assert entered.wait(2)
        for sequence in range(2, 19):
            assert writer.submit(frame(sequence, sequence + 9), 0)
        writer.request_stop()
        release.set()
        status = writer.close()
        assert groups == [1, 8] and journal_groups == [1, 8]
        assert status["closed"] and status["submitted"] == status["accepted"] == 18
        assert status["written"] == 1 and status["dropped"] == 17 and status["pending_bytes"] == 0
        assert writer._queue.unfinished_tasks == 0
        assert "partial session preserved" in status["error"] and "private" not in status["error"]
        replay = CameraRunReplay(writer.folder)
        assert replay.footer is None and len(replay.frames) == 1
        assert replay.read_frame(replay.frames[0]) == frame(1, 10).jpeg
    finally:
        release.set()
        writer.close()


def test_failed_journal_sync_does_not_publish_written_frames(tmp_path, monkeypatch):
    from carveracontroller.machine import camera_run

    writer = CameraRunWriter(tmp_path, str(uuid4()))
    journal_fd = writer._journal.fileno()
    original = camera_run.os.fsync

    def fail_journal_sync(fd):
        if fd == journal_fd:
            raise OSError("private volume details")
        return original(fd)

    monkeypatch.setattr(camera_run.os, "fsync", fail_journal_sync)
    assert writer.submit(frame(1, 10), 0)
    status = writer.close()
    assert status["closed"] and status["written"] == 0 and status["dropped"] == 1
    assert status["pending_bytes"] == 0 and writer._queue.unfinished_tasks == 0
    assert "partial session preserved" in status["error"] and "private" not in status["error"]
    # Buffered lines may be readable after a failed sync. They have no final
    # receipt and do not substitute for a successful durability acknowledgement.
    assert CameraRunReplay(writer.folder).footer is None


def test_camera_bundle_roundtrip_deduplicates_assets_and_preserves_existing_files(tmp_path):
    from carveracontroller.machine.camera_run import export_camera_bundle, import_camera_bundle

    writer = CameraRunWriter(tmp_path / "source", str(uuid4()))
    writer.submit(frame(1, 10), 0)
    writer.submit(frame(2, 11), 0)
    writer.close()
    original = CameraRunReplay(writer.folder)
    bundle = tmp_path / "camera.cvcamera"
    receipt = export_camera_bundle(original, bundle)
    assert receipt["frames"] == 2 and receipt["assets"] == 1
    saved = bundle.read_bytes()
    with pytest.raises(FileExistsError):
        export_camera_bundle(original, bundle)
    assert bundle.read_bytes() == saved
    installed = import_camera_bundle(bundle, tmp_path / "destination", writer.folder.parent.name)
    assert installed.folder != original.folder
    assert installed.manifest_digest == original.manifest_digest
    assert installed.frames == original.frames
    assert installed.read_frame(installed.frames[0]) == original.read_frame(original.frames[0])
    second = import_camera_bundle(bundle, tmp_path / "destination", writer.folder.parent.name)
    assert second.folder != installed.folder
    assert installed.read_frame(installed.frames[1]) == frame(2, 11).jpeg


@pytest.mark.parametrize("mutation", ["unexpected", "traversal", "missing", "corrupt", "duplicate", "compressed"])
def test_camera_bundle_rejects_invalid_members_before_installation(tmp_path, mutation):
    import zipfile

    from carveracontroller.machine.camera_run import export_camera_bundle, import_camera_bundle

    writer = CameraRunWriter(tmp_path / "source", str(uuid4()))
    writer.submit(frame(1, 10), 0)
    writer.close()
    replay = CameraRunReplay(writer.folder)
    bundle = tmp_path / "valid.cvcamera"
    export_camera_bundle(replay, bundle)
    with zipfile.ZipFile(bundle) as archive:
        contents = {entry.filename: archive.read(entry) for entry in archive.infolist()}
    asset = replay.frames[0]["sha256"] + ".jpg"
    if mutation == "unexpected":
        contents["unrelated.txt"] = b"unexpected"
    elif mutation == "traversal":
        contents["../outside.jpg"] = contents.pop(asset)
    elif mutation == "missing":
        del contents[asset]
    elif mutation == "corrupt":
        contents[asset] = b"x" * len(contents[asset])
    broken = tmp_path / "broken.cvcamera"
    compression = zipfile.ZIP_DEFLATED if mutation == "compressed" else zipfile.ZIP_STORED
    with zipfile.ZipFile(broken, "w", compression=compression) as archive:
        for name, data in contents.items():
            archive.writestr(name, data)
        if mutation == "duplicate":
            with pytest.warns(UserWarning):
                archive.writestr("frames.jsonl", contents["frames.jsonl"])
    destination = tmp_path / "destination"
    with pytest.raises(ValueError):
        import_camera_bundle(broken, destination, replay.header["recording_session_id"])
    assert not destination.exists()
    assert not (tmp_path / "outside.jpg").exists()


def test_camera_bundle_wrong_session_and_retention_limit_do_not_install(tmp_path, monkeypatch):
    from carveracontroller.machine import camera_run

    writer = CameraRunWriter(tmp_path / "source", str(uuid4()))
    writer.submit(frame(1, 10), 0)
    writer.close()
    replay = CameraRunReplay(writer.folder)
    bundle = tmp_path / "camera.cvcamera"
    camera_run.export_camera_bundle(replay, bundle)
    destination = tmp_path / "destination"
    with pytest.raises(ValueError, match="different status session"):
        camera_run.import_camera_bundle(bundle, destination, str(uuid4()))
    monkeypatch.setattr(camera_run, "MAX_BUNDLE_BYTES", 10)
    with pytest.raises(ValueError, match="retention budget"):
        camera_run.import_camera_bundle(bundle, destination, replay.header["recording_session_id"])
    assert not destination.exists()


@pytest.mark.parametrize(
    "record_index,key,value",
    [
        (0, "recording_session_id", 123),
        (0, "part_id", None),
        (0, "created_utc", True),
        (1, "received_at", True),
        (1, "server_captured_at", "1.0"),
        (1, "sequence", False),
        (1, "generation", -1),
        (1, "size", [True, 1]),
        (1, "size_bytes", True),
        (2, "accepted", True),
        (2, "closed", "true"),
        (2, "error", None),
    ],
)
def test_replay_rejects_malformed_fields_even_with_valid_digest_chain(tmp_path, record_index, key, value):
    import hashlib

    writer = CameraRunWriter(tmp_path, str(uuid4()))
    writer.submit(frame(1, 10), 0)
    writer.close()
    records = [json.loads(line) for line in (writer.folder / "frames.jsonl").read_bytes().splitlines()]
    records[record_index][key] = value
    encoded = []
    chain = "0" * 64
    for record in records:
        record.pop("chain_sha256")
        data = json.dumps(record, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
        chain = hashlib.sha256(chain.encode() + data).hexdigest()
        record["chain_sha256"] = chain
        encoded.append(json.dumps(record).encode())
    with pytest.raises(ValueError):
        CameraRunReplay(writer.folder, manifest_bytes=b"\n".join(encoded) + b"\n")
    # Validation of external data does not alter the source or retire its worker.
    assert not writer.thread.is_alive()
    assert CameraRunReplay(writer.folder).read_frame(CameraRunReplay(writer.folder).frames[0]) == frame(1, 10).jpeg
