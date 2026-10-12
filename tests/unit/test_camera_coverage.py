import pytest

from carveracontroller.machine.camera_coverage import parse_correspondences, review_coverage, review_held_out
from carveracontroller.machine.camera_registration import (
    CameraIntrinsics,
    CameraPose,
    CameraRegistration,
    RegistrationObservation,
)


def test_hull_area_rejects_bounding_box_as_coverage_proxy():
    # A diagonal crosses most of both image axes but covers no area.
    points = [RegistrationObservation((i, i, 0), (i, i)) for i in (1, 40, 99)]
    review = review_coverage(points, (100, 100))
    assert review.image_fraction == 0
    rectangle = parse_correspondences("0 0 0 10 10\n1 0 0 90 10\n1 1 0 90 90\n0 1 0 10 90", (100, 100))
    review = review_coverage((*rectangle, rectangle[0]), (100, 100))
    assert review.image_fraction == pytest.approx(0.64)
    assert len(review.hull) == 4 and review.z_range_mm == (0, 0)


def test_per_point_errors_and_height_span_retain_correspondence_order():
    registration = CameraRegistration(CameraIntrinsics(100, 100, 100, 100, 50, 50), CameraPose((0, 0, 0), (0, 0, 100)))
    points = [RegistrationObservation((0, 0, 0), (50, 50)), RegistrationObservation((10, 0, 20), (50, 50))]
    review = review_coverage(points, (100, 100), registration)
    assert review.residuals_px == pytest.approx((0, 100 * 10 / 120))
    assert review.z_range_mm == (0, 20)
    with pytest.raises(ValueError, match="sizes differ"):
        review_coverage(points, (200, 100), registration)


@pytest.mark.parametrize("text", ["0 0 nan 1 1", "0 0 0 100 1", "0 0 0 1", "0 0 0 a 1"])
def test_invalid_input_identifies_source_line_without_partial_review(text):
    with pytest.raises(ValueError, match="Line 2"):
        parse_correspondences("0 0 0 10 10\n" + text, (100, 100))


def test_empty_and_excessive_correspondences_are_bounded():
    assert review_coverage((), (100, 100)).z_range_mm is None
    with pytest.raises(ValueError, match="128"):
        parse_correspondences("\n".join(["0 0 0 10 10"] * 129), (100, 100))


def test_fitting_residuals_do_not_replace_held_out_accuracy():
    model = CameraRegistration(CameraIntrinsics(100, 100, 100, 100, 50, 50), CameraPose((0, 0, 0), (0, 0, 100)))
    fitting = parse_correspondences("0 0 0 50 50", (100, 100))
    checks = parse_correspondences("10 0 0 63 50\n0 10 0 50 64", (100, 100))
    assert review_coverage(fitting, (100, 100), model).residuals_px == (0,)
    before = model
    result = review_held_out(fitting, checks, (100, 100), model, 3)
    assert result.residuals_px == pytest.approx((3, 4))
    assert result.rms_px == pytest.approx((12.5) ** 0.5)
    assert result.maximum_px == 4 and result.within_limit is False
    assert model is before
    assert review_held_out(fitting, checks, (100, 100), model).within_limit is None
    assert review_held_out(fitting, checks, (100, 100), model, 4).within_limit is True


@pytest.mark.parametrize("checks", ["0 0 0 51 50", "1 0 0 50 50", "1 0 0 51 50\n1 0 0 52 50"])
def test_reused_fit_or_duplicate_check_points_are_refused(checks):
    model = CameraRegistration(CameraIntrinsics(100, 100, 100, 100, 50, 50), CameraPose((0, 0, 0), (0, 0, 100)))
    with pytest.raises(ValueError, match="must differ"):
        review_held_out(
            parse_correspondences("0 0 0 50 50", (100, 100)),
            parse_correspondences(checks, (100, 100)),
            (100, 100),
            model,
        )


@pytest.mark.parametrize("limit", [True, 0, -1, float("nan"), float("inf"), 32769])
def test_invalid_held_out_error_limits_are_refused(limit):
    model = CameraRegistration(CameraIntrinsics(100, 100, 100, 100, 50, 50), CameraPose((0, 0, 0), (0, 0, 100)))
    with pytest.raises(ValueError, match="limit"):
        review_held_out(
            parse_correspondences("0 0 0 50 50", (100, 100)),
            parse_correspondences("1 0 0 51 50", (100, 100)),
            (100, 100),
            model,
            limit,
        )
