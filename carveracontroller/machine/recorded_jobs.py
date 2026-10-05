"""Portable recorded selections and observations; import never commands a machine."""

import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from carveracontroller.machine.camera_run import (
    MAX_BUNDLE_BYTES,
    export_camera_bundle,
    import_camera_bundle_stream,
    validate_camera_bundle_stream,
)
from carveracontroller.machine.job_packages import MAX_TOTAL, load_package
from carveracontroller.machine.recording_setup import validate_setup_binding
from carveracontroller.machine.run_recording import MAX_ARCHIVE_BYTES, RecordingReplay

MAX_RUN_BYTES = MAX_BUNDLE_BYTES + 2 * MAX_ARCHIVE_BYTES + MAX_TOTAL + 65536
LIMITS = {
    "manifest.json": 65536,
    "status.cvrun": MAX_ARCHIVE_BYTES,
    "program.nc": MAX_ARCHIVE_BYTES,
    "camera.cvcamera": MAX_BUNDLE_BYTES,
    "setup.cvjob": MAX_TOTAL,
}


@dataclass(frozen=True)
class LoadedRecordedJob:
    replay: RecordingReplay
    program: Path
    camera: object
    folder: Path
    setup_archive: object = None


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _program_bytes(replay, filename):
    identity = replay.payload.get("context", {}).get("program")
    if identity is None:
        raise ValueError("A full run requires the selected program binding")
    with Path(filename).open("rb") as source:
        data = source.read(MAX_ARCHIVE_BYTES + 1)
    if len(data) != identity["size_bytes"] or _hash(data) != identity["sha256"]:
        raise ValueError("Program bytes do not match the recorded selection")
    data.decode("utf-8", errors="strict")
    if b"\x00" in data:
        raise ValueError("Full run preview requires a decoded text program")
    return data


def _stream_digest(source):
    digest = hashlib.sha256()
    while data := source.read(1024 * 1024):
        digest.update(data)
    return digest.hexdigest()


def _member_digest(archive, name):
    with archive.open(name) as source:
        return _stream_digest(source)


def _inspect(archive):
    infos = archive.infolist()
    names = [entry.filename for entry in infos]
    if len(names) not in (3, 4, 5) or len(names) != len(set(names)) or set(names) - set(LIMITS):
        raise ValueError("Invalid recorded-run member set")
    if not {"manifest.json", "status.cvrun", "program.nc"} <= set(names):
        raise ValueError("Recorded run is missing required members")
    for entry in infos:
        mode = entry.external_attr >> 16
        if (
            entry.compress_type != zipfile.ZIP_STORED
            or entry.flag_bits & 1
            or entry.is_dir()
            or mode & 0o170000 not in (0, 0o100000)
            or not 0 <= entry.file_size <= LIMITS[entry.filename]
        ):
            raise ValueError("Unsupported recorded-run member or size")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate recorded-run manifest key")
            result[key] = value
        return result

    manifest = json.loads(archive.read("manifest.json"), object_pairs_hook=unique)
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"schema", "session_id", "members"}
        or type(manifest["schema"]) is not int
        or manifest["schema"] != 1
        or not isinstance(manifest["members"], dict)
        or set(manifest["members"]) != set(names) - {"manifest.json"}
    ):
        raise ValueError("Invalid recorded-run manifest")
    for name, metadata in manifest["members"].items():
        if (
            not isinstance(metadata, dict)
            or set(metadata) != {"sha256", "size_bytes"}
            or type(metadata["size_bytes"]) is not int
            or metadata["size_bytes"] != archive.getinfo(name).file_size
            or metadata["sha256"] != _member_digest(archive, name)
        ):
            raise ValueError("Recorded-run member digest/size differs")
    replay = RecordingReplay(archive.read("status.cvrun"))
    if replay.payload["session_id"] != manifest["session_id"]:
        raise ValueError("Recorded-run session identity differs")
    data = archive.read("program.nc")
    identity = replay.payload.get("context", {}).get("program")
    if identity is None or len(data) != identity["size_bytes"] or _hash(data) != identity["sha256"]:
        raise ValueError("Program bytes do not match the recorded selection")
    data.decode("utf-8", errors="strict")
    if b"\x00" in data:
        raise ValueError("Full run preview requires a decoded text program")
    configuration = replay.payload["context"].get("configuration")
    if (configuration is not None) != ("setup.cvjob" in names):
        raise ValueError("Recorded setup archive is missing or unbound")
    if configuration is not None:
        metadata = manifest["members"]["setup.cvjob"]
        if metadata["sha256"] != configuration["sha256"] or metadata["size_bytes"] != configuration["size_bytes"]:
            raise ValueError("Recorded setup identity differs")
        with archive.open("setup.cvjob") as source:
            loaded_setup = load_package(source)
        validate_setup_binding(loaded_setup.package, replay.payload["context"])
    if "camera.cvcamera" in names:
        with archive.open("camera.cvcamera") as source:
            validate_camera_bundle_stream(source, replay.payload["session_id"])
    return replay, data


def export_recorded_job(replay, program_file, filename, camera=None, setup_archive=None):
    """Save exact selected text program, status and optional matching camera part."""
    program = _program_bytes(replay, program_file)
    status = replay.export_bytes()
    session = replay.payload["session_id"]
    if camera is not None and camera.header["recording_session_id"] != session:
        raise ValueError("Camera part belongs to a different status session")
    configuration = replay.payload["context"].get("configuration")
    if (configuration is not None) != (setup_archive is not None):
        raise ValueError("Retained setup archive is missing or unbound")
    setup_metadata = None
    if configuration is not None:
        with Path(setup_archive).open("rb") as source:
            if (
                os.fstat(source.fileno()).st_size != configuration["size_bytes"]
                or _stream_digest(source) != configuration["sha256"]
            ):
                raise ValueError("Recorded setup archive bytes differ")
        validate_setup_binding(load_package(setup_archive).package, replay.payload["context"])
        setup_metadata = {"sha256": configuration["sha256"], "size_bytes": configuration["size_bytes"]}
    target = Path(filename)
    # Camera scratch is beside the requested destination to avoid consuming a
    # different volume; the original part remains authoritative and untouched.
    with tempfile.TemporaryDirectory(prefix=".run-bundle-", dir=target.parent) as scratch:
        camera_file = Path(scratch) / "camera.cvcamera"
        if camera is not None:
            export_camera_bundle(camera, camera_file)
        members = {
            "status.cvrun": {"sha256": _hash(status), "size_bytes": len(status)},
            "program.nc": {"sha256": _hash(program), "size_bytes": len(program)},
        }
        if camera is not None:
            with camera_file.open("rb") as source:
                members["camera.cvcamera"] = {
                    "sha256": _stream_digest(source),
                    "size_bytes": camera_file.stat().st_size,
                }
        if setup_metadata is not None:
            members["setup.cvjob"] = setup_metadata
        manifest = {"schema": 1, "session_id": session, "members": members}
        with target.open("xb") as destination:
            with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_STORED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest, sort_keys=True).encode())
                archive.writestr("status.cvrun", status)
                archive.writestr("program.nc", program)
                if camera is not None:
                    archive.write(camera_file, "camera.cvcamera")
                if setup_archive is not None:
                    archive.write(setup_archive, "setup.cvjob")
            destination.flush()
            os.fsync(destination.fileno())
    with target.open("rb") as source:
        if os.fstat(source.fileno()).st_size > MAX_RUN_BYTES:
            raise ValueError("Recorded run exceeds retention budget")
        with zipfile.ZipFile(source) as archive:
            verified, _ = _inspect(archive)
    return {
        "session_id": verified.payload["session_id"],
        "camera_included": camera is not None,
        "program_sha256": verified.payload["context"]["program"]["sha256"],
    }


def import_recorded_job(filename, directory):
    with Path(filename).open("rb") as source:
        if os.fstat(source.fileno()).st_size > MAX_RUN_BYTES:
            raise ValueError("Recorded run exceeds retention budget")
        with zipfile.ZipFile(source) as archive:
            replay, program = _inspect(archive)
            folder = Path(directory) / ("run-" + str(uuid4()))
            folder.mkdir(parents=True, exist_ok=False)
            for name, data in (("program.nc", program), ("status.cvrun", replay.export_bytes())):
                with (folder / name).open("xb") as output:
                    output.write(data)
                    output.flush()
                    os.fsync(output.fileno())
            setup_archive = None
            if "setup.cvjob" in archive.namelist():
                setup_archive = folder / "setup.cvjob"
                with archive.open("setup.cvjob") as incoming, setup_archive.open("xb") as outgoing:
                    while chunk := incoming.read(1024 * 1024):
                        outgoing.write(chunk)
                    outgoing.flush()
                    os.fsync(outgoing.fileno())
                with setup_archive.open("rb") as saved:
                    if _stream_digest(saved) != replay.payload["context"]["configuration"]["sha256"]:
                        raise ValueError("Installed setup archive differs")
            camera = None
            if "camera.cvcamera" in archive.namelist():
                with archive.open("camera.cvcamera") as camera_source:
                    camera = import_camera_bundle_stream(camera_source, folder / "camera", replay.payload["session_id"])
    restored = RecordingReplay((folder / "status.cvrun").read_bytes())
    _program_bytes(restored, folder / "program.nc")
    if restored.export_bytes() != replay.export_bytes():
        raise ValueError("Installed run status differs")
    return LoadedRecordedJob(restored, folder / "program.nc", camera, folder, setup_archive)
