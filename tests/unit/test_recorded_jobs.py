import hashlib
import json
import zipfile
from types import SimpleNamespace
from uuid import uuid4

import pytest

from carveracontroller.machine.camera_run import CameraRunReplay, CameraRunWriter
from carveracontroller.machine.recorded_jobs import export_recorded_job, import_recorded_job
from carveracontroller.machine.run_recording import RecordingReplay, RunRecording, selected_context


@pytest.fixture
def selected_run(tmp_path):
    program = tmp_path / "selected.nc"
    program.write_bytes(b"G21\r\nG90\r\nG1 X1 F100\r\n")
    setup = {
        "work_offset_mm": [1, 2, 3],
        "stock_origin_mm": [0, 0, 0],
        "stock_size_mm": [10, 20, 8],
        "alignment_confirmed": False,
    }
    record = RunRecording(context=selected_context(program, setup))
    record.capture_status("Idle", {"MPos": [1, 2, 3]}, 10, 1000, 1)
    writer = CameraRunWriter(tmp_path / "camera", record.session_id)
    writer.submit(
        SimpleNamespace(jpeg=b"\xff\xd8test\xff\xd9", size=(1, 1), sequence=1, received_at=10, captured_at=None), 0
    )
    writer.close()
    return RecordingReplay(record.export_bytes()), program, CameraRunReplay(writer.folder)


@pytest.mark.parametrize("with_camera", [False, True])
def test_full_run_roundtrip_preserves_program_clocks_setup_and_camera(tmp_path, selected_run, with_camera):
    replay, program, camera = selected_run
    bundle = tmp_path / "run.cvsession"
    receipt = export_recorded_job(replay, program, bundle, camera if with_camera else None)
    assert receipt["camera_included"] is with_camera
    original = bundle.read_bytes()
    with pytest.raises(FileExistsError):
        export_recorded_job(replay, program, bundle, camera if with_camera else None)
    assert bundle.read_bytes() == original
    loaded = import_recorded_job(bundle, tmp_path / "destination")
    assert loaded.program.read_bytes() == program.read_bytes()
    assert loaded.replay.export_bytes() == replay.export_bytes()
    assert loaded.replay.payload["context"]["setup"]["alignment_confirmed"] is False
    if with_camera:
        assert loaded.camera.manifest_digest == camera.manifest_digest
        assert loaded.camera.read_frame(loaded.camera.frames[0]) == camera.read_frame(camera.frames[0])
    else:
        assert loaded.camera is None
    second = import_recorded_job(bundle, tmp_path / "destination")
    assert loaded.folder != second.folder


@pytest.mark.parametrize("mutation", ["digest", "program_binding", "session", "unexpected", "traversal"])
def test_full_run_corruption_rejected_before_installation(tmp_path, selected_run, mutation):
    replay, program, camera = selected_run
    good = tmp_path / "good.cvsession"
    export_recorded_job(replay, program, good, camera)
    with zipfile.ZipFile(good) as archive:
        data = {name: archive.read(name) for name in archive.namelist()}
    manifest = json.loads(data["manifest.json"])
    if mutation in ("digest", "program_binding"):
        data["program.nc"] = b"G21\nG1 X99\n"
        if mutation == "program_binding":
            manifest["members"]["program.nc"] = {
                "sha256": hashlib.sha256(data["program.nc"]).hexdigest(),
                "size_bytes": len(data["program.nc"]),
            }
    elif mutation == "session":
        manifest["session_id"] = str(uuid4())
    elif mutation == "unexpected":
        data["unrelated.txt"] = b"extra"
    else:
        data["../outside.nc"] = data.pop("program.nc")
    data["manifest.json"] = json.dumps(manifest).encode()
    broken = tmp_path / "broken.cvsession"
    with zipfile.ZipFile(broken, "w") as archive:
        for name, value in data.items():
            archive.writestr(name, value)
    destination = tmp_path / "installed"
    with pytest.raises(ValueError):
        import_recorded_job(broken, destination)
    assert not destination.exists()
    assert not (tmp_path / "outside.nc").exists()


def test_full_run_rejects_unbound_program_and_foreign_camera(tmp_path, selected_run):
    replay, program, camera = selected_run
    program.write_text("G21\n")
    with pytest.raises(ValueError, match="do not match"):
        export_recorded_job(replay, program, tmp_path / "changed.cvsession", camera)
    assert not (tmp_path / "changed.cvsession").exists()
    with pytest.raises(ValueError, match="binding"):
        export_recorded_job(RecordingReplay(RunRecording().export_bytes()), program, tmp_path / "unbound.cvsession")
    camera.header["recording_session_id"] = str(uuid4())
    program.write_bytes(b"G21\r\nG90\r\nG1 X1 F100\r\n")
    with pytest.raises(ValueError, match="different status session"):
        export_recorded_job(replay, program, tmp_path / "foreign.cvsession", camera)


def test_rehashed_outer_bundle_cannot_bind_a_foreign_camera_part(tmp_path, selected_run):
    from carveracontroller.machine.camera_run import export_camera_bundle

    replay, program, camera = selected_run
    bundle = tmp_path / "original.cvsession"
    export_recorded_job(replay, program, bundle, camera)
    foreign_writer = CameraRunWriter(tmp_path / "foreign", str(uuid4()))
    foreign_writer.close()
    foreign_bundle = tmp_path / "foreign.cvcamera"
    export_camera_bundle(CameraRunReplay(foreign_writer.folder), foreign_bundle)
    with zipfile.ZipFile(bundle) as archive:
        data = {name: archive.read(name) for name in archive.namelist()}
    data["camera.cvcamera"] = foreign_bundle.read_bytes()
    manifest = json.loads(data["manifest.json"])
    manifest["members"]["camera.cvcamera"] = {
        "sha256": hashlib.sha256(data["camera.cvcamera"]).hexdigest(),
        "size_bytes": len(data["camera.cvcamera"]),
    }
    data["manifest.json"] = json.dumps(manifest).encode()
    forged = tmp_path / "forged.cvsession"
    with zipfile.ZipFile(forged, "w") as archive:
        for name, content in data.items():
            archive.writestr(name, content)
    with pytest.raises(ValueError, match="different status session"):
        import_recorded_job(forged, tmp_path / "installed")
    assert not (tmp_path / "installed").exists()
