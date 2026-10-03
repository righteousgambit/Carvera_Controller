import math

import pytest

from carveracontroller.machine.camera_registration import (
    CameraIntrinsics,
    CameraPose,
    CameraRegistration,
    RegistrationObservation,
    calibrate_camera,
    fit_camera_pose,
)


def camera():
    return CameraIntrinsics(1920, 1080, 1400, 1390, 955, 543, (-0.12, 0.025, 0.001, -0.002, 0.001))


def observations(registration, points):
    return [RegistrationObservation(p, registration.project(p)) for p in points]


def plate():
    return [(x * 19.05, y * 19.05, 0.0) for y in range(-3, 4) for x in range(-4, 5)]


def test_lens_inversion_and_raised_stock_projection():
    reg = CameraRegistration(camera(), CameraPose((0.4, -0.2, 0.05), (10.0, -20.0, 400.0)))
    point = (35.0, 20.0, 50.0)
    x, y, z = reg.pose.transform(point)
    assert reg.intrinsics.undistort(reg.project(point)) == pytest.approx((x / z, y / z), abs=1e-9)
    assert math.dist(reg.project(point), reg.project((35.0, 20.0, 0.0))) > 20
    assert CameraRegistration.from_dict(reg.to_dict()).project(point) == reg.project(point)
    with pytest.raises(ValueError, match="behind"):
        CameraRegistration(camera(), CameraPose((0.0, 0.0, 0.0), (0.0, 0.0, -400.0))).project(point)


def test_planar_saunders_holes_recover_pose_and_predict_unfitted_height():
    expected = CameraRegistration(camera(), CameraPose((0.55, -0.25, 0.08), (15.0, -30.0, 480.0)))
    result = fit_camera_pose(camera(), observations(expected, plate()))
    assert result.rms_px < 1e-6
    assert result.registration.pose.translation == pytest.approx(expected.pose.translation, abs=1e-5)
    assert result.registration.project((50.0, 30.0, 60.0)) == pytest.approx(
        expected.project((50.0, 30.0, 60.0)), abs=1e-5
    )
    assert any("Planar" in x for x in result.warnings)


def test_nonplanar_fit_and_degenerate_rejection():
    expected = CameraRegistration(camera(), CameraPose((0.25, -0.3, 0.12), (8.0, 4.0, 400.0)))
    points = [(x * 30.0, y * 30.0, z * 20.0) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
    result = fit_camera_pose(camera(), observations(expected, points))
    assert result.rms_px < 1e-5
    with pytest.raises(ValueError, match="Degenerate"):
        fit_camera_pose(camera(), observations(expected, [(float(i), 0.0, 0.0) for i in range(8)]))


def test_bad_correspondence_is_reported_and_robust_fit_preserves_pose():
    expected = CameraRegistration(camera(), CameraPose((0.4, -0.2, 0.05), (10.0, -20.0, 400.0)))
    samples = observations(expected, plate())
    first = samples[0]
    samples[0] = RegistrationObservation(first.world_mm, (first.pixel[0] + 50, first.pixel[1] - 40))
    result = fit_camera_pose(camera(), samples)
    assert 0 in result.outlier_indices
    assert result.max_px > 50
    assert math.dist(result.registration.project((0.0, 0.0, 50.0)), expected.project((0.0, 0.0, 50.0))) < 2


def test_intrinsic_calibration_requires_view_diversity_and_recovers_focal_length():
    true = camera()
    points = plate()
    poses = [
        CameraPose((0.4, -0.2, 0.05), (10.0, -20.0, 400.0)),
        CameraPose((-0.3, 0.4, -0.1), (-20.0, 5.0, 460.0)),
        CameraPose((0.2, 0.5, 0.2), (20.0, -10.0, 500.0)),
        CameraPose((-0.5, -0.3, 0.1), (0.0, 15.0, 420.0)),
    ]
    boards = [observations(CameraRegistration(true, p), points) for p in poses]
    prior = CameraIntrinsics(1920, 1080, 1350, 1340, 960, 540, true.distortion)
    fitted, results = calibrate_camera(prior, boards, fit_distortion=False)
    assert fitted.fx == pytest.approx(true.fx, abs=0.01)
    assert fitted.fy == pytest.approx(true.fy, abs=0.01)
    assert fitted.cx == pytest.approx(true.cx, abs=0.01)
    assert max(r.rms_px for r in results) < 1e-4
    with pytest.raises(ValueError, match="tilts"):
        calibrate_camera(prior, [boards[0]] * 3)


def test_invalid_records_and_noninvertible_distortion():
    with pytest.raises(ValueError):
        CameraIntrinsics(0, 1080, 1000, 1000, 500, 500)
    with pytest.raises(ValueError):
        RegistrationObservation((float("nan"), 0.0, 0.0), (20.0, 20.0))
    with pytest.raises(ValueError):
        CameraRegistration.from_dict({"schema_version": 2})


def test_joint_lens_distortion_calibration_recovers_actual_image_model():
    true = camera()
    points = [(x * 30.0, y * 30.0, 0.0) for y in range(-3, 4) for x in range(-4, 5)]
    poses = [
        CameraPose((0.4, -0.2, 0.05), (10.0, -20.0, 350.0)),
        CameraPose((-0.3, 0.4, -0.1), (-20.0, 5.0, 410.0)),
        CameraPose((0.2, 0.5, 0.2), (20.0, -10.0, 450.0)),
        CameraPose((-0.5, -0.3, 0.1), (0.0, 15.0, 380.0)),
    ]
    boards = [observations(CameraRegistration(true, p), points) for p in poses]
    prior = CameraIntrinsics(1920, 1080, 1380, 1380, 960, 540)
    fitted, results = calibrate_camera(prior, boards)
    assert max(r.rms_px for r in results) < 1e-3
    assert fitted.fx == pytest.approx(true.fx, abs=0.1)
    assert fitted.distortion == pytest.approx(true.distortion, abs=0.002)
    assert all(0 < r.geometry_condition < 1 for r in results)
