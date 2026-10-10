import copy
import hashlib
import io
from dataclasses import replace

import pytest
from PIL import Image

from carveracontroller.machine.camera_lens_study import (
    MAX_CAPTURE_BYTES,
    MAX_STUDY_BYTES,
    CameraLensStudy,
    LensCapture,
    decode_lens_study,
    read_lens_study,
    write_lens_study,
)
from carveracontroller.machine.camera_registration import (
    CameraIntrinsics,
    CameraPose,
    CameraRegistration,
    calibrate_camera,
    fit_camera_pose,
)
from tests.unit.test_camera_calibration_file import reference
from tests.unit.test_camera_registration import observations


def study():
    intrinsic = CameraIntrinsics(24, 18, 20, 21, 12, 9)
    base = reference()
    captures = []
    points = [(x * 10.0, y * 10.0, 0.0) for x in (-2, -1, 1, 2) for y in (-1, 0, 1)]
    for index, rotation in enumerate(((0.4, -0.2, 0.05), (-0.3, 0.4, -0.1), (0.2, 0.5, 0.2))):
        buffer = io.BytesIO()
        Image.new("RGB", (24, 18), (40 + 40 * index, 90, 120)).save(buffer, format="JPEG")
        jpeg = buffer.getvalue()
        with Image.open(io.BytesIO(jpeg)) as image:
            pixels = image.convert("RGB").tobytes()
        frame = replace(base.frame, pixels=pixels, jpeg=jpeg, sequence=index + 1)
        captured = replace(base, frame=frame)
        registration = CameraRegistration(intrinsic, CameraPose(rotation, (0.0, 0.0, 100.0 + index * 10)))
        captures.append(LensCapture(captured, tuple(observations(registration, points))))
    return CameraLensStudy(CameraIntrinsics(24, 18, 19, 20, 12, 9), tuple(captures), False)


def test_measurements_roundtrip_with_exact_images_original_prior_and_no_cached_fit(tmp_path):
    original = study()
    path = tmp_path / "measured.cvlens"
    digest = write_lens_study(path, original)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    restored = read_lens_study(path)
    assert restored == original
    assert restored.to_dict()["physical_qualification"] == "unqualified"
    assert "cached" in restored.to_dict()["fit_policy"]
    with pytest.raises(FileExistsError):
        write_lens_study(path, original)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    intrinsic, results = calibrate_camera(
        restored.prior, [c.observations for c in restored.captures], fit_distortion=restored.fit_distortion
    )
    assert intrinsic.fx == pytest.approx(20, abs=0.001)
    assert intrinsic.fy == pytest.approx(21, abs=0.001)
    assert max(result.rms_px for result in results) < 1e-5


@pytest.mark.parametrize(
    "mutation", ["schema", "bool", "number", "source", "generation", "duplicate", "size", "count", "pixel", "hash"]
)
def test_untrusted_study_rejects_malformed_or_mixed_evidence(mutation):
    data = copy.deepcopy(study().to_dict())
    if mutation == "schema":
        data["schema"] = True
    elif mutation == "bool":
        data["fit_distortion"] = "true"
    elif mutation == "number":
        data["prior"]["fx"] = "20"
    elif mutation == "source":
        data["captures"][1]["reference"]["source_sha256"] = "b" * 64
    elif mutation == "generation":
        data["captures"][1]["reference"]["camera_generation"] += 1
    elif mutation == "duplicate":
        data["captures"][1] = data["captures"][0]
    elif mutation == "size":
        data["prior"]["width"] = 25
    elif mutation == "count":
        data["captures"][1]["observations"] = data["captures"][1]["observations"][:7]
    elif mutation == "pixel":
        data["captures"][1]["observations"][0]["pixel"] = [25, 0]
    else:
        data["captures"][1]["reference"]["jpeg_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        decode_lens_study(data)


def test_partial_study_is_saveable_but_solver_requires_three_views(tmp_path):
    original = study()
    partial = replace(original, captures=original.captures[:1])
    path = tmp_path / "partial.cvlens"
    write_lens_study(path, partial)
    assert read_lens_study(path) == partial
    with pytest.raises(ValueError, match="3 to 12"):
        calibrate_camera(partial.prior, [c.observations for c in partial.captures])


def test_file_and_decoded_image_limits_are_checked_before_unbounded_allocations(tmp_path, monkeypatch):
    path = tmp_path / "oversize.cvlens"
    with path.open("wb") as source:
        source.truncate(MAX_STUDY_BYTES + 1)
    with pytest.raises(ValueError, match="48 MB"):
        read_lens_study(path)
    data = study().to_dict()
    decoded = []

    def decode_reference(value):
        decoded.append(value)
        base = reference()
        return replace(base, frame=replace(base.frame, size=(4096, 4096)))

    for capture in data["captures"]:
        capture["reference"]["size"] = [4096, 4096]
    monkeypatch.setattr("carveracontroller.machine.camera_lens_study.CalibrationReference.from_dict", decode_reference)
    with pytest.raises(ValueError, match="96 MB"):
        decode_lens_study(data)
    assert len(decoded) == 1
    assert 4096 * 4096 * 3 * 2 + len(reference().frame.jpeg) > MAX_CAPTURE_BYTES


@pytest.mark.parametrize("value", [True, "1", float("nan"), float("inf"), 10**400])
def test_observation_coordinates_are_not_coerced(value):
    data = study().to_dict()
    data["captures"][0]["observations"][0]["world_mm"][0] = value
    with pytest.raises(ValueError):
        decode_lens_study(data)


def test_cancellation_before_pose_and_during_joint_refinement_retains_inputs(monkeypatch):
    from carveracontroller.machine import camera_registration as backend

    measured = study()
    boards = [c.observations for c in measured.captures]
    before = measured.to_dict()
    with pytest.raises(InterruptedError, match="cancelled"):
        fit_camera_pose(measured.prior, boards[0], cancelled=lambda: True)
    original = backend._refine
    stages = []
    cancelled = False

    def refine(parameters, residual_fn, max_iterations, cancelled_check):
        nonlocal cancelled
        stages.append(len(parameters))
        if len(parameters) > 6:
            calls = 0

            def joint_cancel():
                nonlocal calls, cancelled
                calls += 1
                cancelled = calls > 15
                return cancelled

            return original(parameters, residual_fn, max_iterations, joint_cancel)
        return original(parameters, residual_fn, max_iterations, cancelled_check)

    monkeypatch.setattr(backend, "_refine", refine)
    with pytest.raises(InterruptedError, match="cancelled"):
        calibrate_camera(measured.prior, boards, fit_distortion=False)
    assert cancelled and stages == [6, 6, 6, 22]
    assert measured.to_dict() == before
