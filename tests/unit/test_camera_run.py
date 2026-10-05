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
        original(item, data)

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
