"""Readback-verified declared setup snapshots bound to recording start."""

import hashlib
from pathlib import Path
from uuid import uuid4

from carveracontroller.machine.job_packages import MAX_TOTAL, load_package, retained_camera_calibration, save_package
from carveracontroller.machine.run_recording import RunRecording, selected_context


def validate_setup_binding(job, context):
    identity, setup = context["program"], context["setup"]
    if len(job.program) != identity["size_bytes"] or hashlib.sha256(job.program).hexdigest() != identity["sha256"]:
        raise ValueError("Setup snapshot program differs")
    expected = {
        "size_mm": list(setup["stock_size_mm"]) if setup["stock_size_mm"] is not None else None,
        "origin_mm": list(setup["stock_origin_mm"]),
        "work_offset_mm": list(setup["work_offset_mm"]),
        "alignment_confirmed": setup["alignment_confirmed"],
    }
    if job.stock.get("rotation_deg", 0) != setup.get("stock_rotation_deg", 0):
        raise ValueError("Setup snapshot stock rotation differs")
    if any(job.stock.get(key) != value for key, value in expected.items()):
        raise ValueError("Setup snapshot stock/offset differs")


def bind_recording_setup(filename, setup, job, directory):
    context = selected_context(filename, setup)
    with Path(filename).open("rb") as source:
        program = source.read(16 * 1024 * 1024 + 1)
    if hashlib.sha256(program).hexdigest() != context["program"]["sha256"]:
        raise ValueError("Selected program changed during recording preparation")
    job.program = program
    validate_setup_binding(job, context)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / (str(uuid4()) + ".cvjob")
    save_package(job, archive)
    loaded = load_package(archive)
    validate_setup_binding(loaded.package, context)
    retained_camera_calibration(loaded)
    if archive.stat().st_size > MAX_TOTAL:
        raise ValueError("Setup snapshot exceeds archive budget")
    digest = hashlib.sha256()
    with archive.open("rb") as source:
        while data := source.read(1024 * 1024):
            digest.update(data)
    context["configuration"] = {
        "sha256": digest.hexdigest(),
        "size_bytes": archive.stat().st_size,
        "scope": "declared_setup_assets_at_recording_start",
    }
    # Check selected geometry bytes against the bytes actually retained, rather
    # than treating an earlier preview hash as evidence for a changed CAD file.
    for definition in loaded.package.inspection_plan.get("tool_definitions_mm", []):
        for path_key, digest_key in (
            ("geometry_path", "geometry_sha256"),
            ("holder_geometry_path", "holder_geometry_sha256"),
        ):
            reference, expected = definition.get(path_key), definition.get(digest_key)
            if reference and expected and hashlib.sha256(loaded.asset_bytes[reference]).hexdigest() != expected:
                raise ValueError("Selected tool geometry changed before snapshot")
    return RunRecording(context=context), archive
