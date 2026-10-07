import pytest

from carveracontroller.desktop_components import Action
from tests.integration.conftest import pump_frames
from tests.integration.test_camera_reference import panel


def test_image_review_is_bound_to_frozen_inputs_and_rejects_stale_fit(kivy_app):
    view, _, controller = panel()
    view.capture_reference()
    view.points.text = "0 0 0 12 9\n10 0 0 20 9"
    identity = view._input_identity()
    popup = view.review_points()
    try:
        assert popup.registration_snapshot is None and popup.largest_residual.disabled
        assert "No current fit" in popup.correspondence_detail.text
        popup.correspondence_selector.text = "2/2"
        assert popup.correspondence_image.selected_index == 1
        assert "X Y Z 10 / 0 / 0" in popup.correspondence_detail.text
        assert view._input_identity() == identity
        captured = popup.reference_snapshot
        view.capture_reference()
        view.points.text = "invalid replacement"
        popup.select_correspondence(0)
        assert popup.reference_snapshot is captured
        assert "Image U 12.000 / V 9.000" in popup.correspondence_detail.text
        controller.executeCommand.assert_not_called()
    finally:
        popup.dismiss(animation=False)

    from carveracontroller.machine.camera_calibration_file import decode_calibration
    from tests.unit.test_camera_calibration_file import data

    view.apply_calibration(decode_calibration(data()))
    view.focal.text = "25 25 12 9"
    popup = view.review_points()
    try:
        assert popup.registration_snapshot is None and popup.largest_residual.disabled
    finally:
        popup.dismiss(animation=False)


def test_fitted_review_links_largest_residual_and_exact_pixel_projection(kivy_app):
    from carveracontroller.machine.camera_calibration_file import decode_calibration
    from tests.unit.test_camera_calibration_file import data

    original = data()
    original["observations"].append({"world_mm": [10, 0, 0], "pixel": [20, 9]})
    view, _, controller = panel()
    view.apply_calibration(decode_calibration(original))
    identity = view._input_identity()
    popup = view.review_points()
    try:
        pump_frames(6)
        popup.largest_residual.trigger_action(0)
        assert popup.correspondence_selector.text == "2/2"
        assert "Fitted U 14.000 / V 9.000 px" in popup.correspondence_detail.text
        assert "error 6.000 px" in popup.correspondence_detail.text
        image = popup.correspondence_image
        assert ((20, 9), (14, 9)) in image.overlay_segments
        image.zoom_by(2)
        pump_frames(3)
        point = image.image_pixel_to_local((20, 9))
        assert point is not None
        assert image.local_to_image_pixel(point) == pytest.approx((20, 9), abs=1e-9)
        popup.select_correspondence(-10)
        assert image.selected_index == 0
        popup.select_correspondence(1000)
        assert image.selected_index == 1
        assert view._input_identity() == identity
        controller.executeCommand.assert_not_called()
    finally:
        popup.dismiss(animation=False)


def test_correspondence_review_requires_valid_reference_and_inputs():
    view, _, controller = panel()
    assert view.review_points() is None
    assert "Capture a reference" in view.note.text
    view.capture_reference()
    assert view.review_points() is None
    assert "Enter correspondences" in view.note.text
    view.points.text = "0 0 0 999 9"
    assert view.review_points() is None
    assert "inside the frozen image" in view.note.text
    view.running = True
    assert view.review_points() is None
    assert "Wait" in view.note.text
    controller.executeCommand.assert_not_called()


def test_border_correspondence_retains_visible_in_image_markers(kivy_app):
    view, _, controller = panel()
    view.capture_reference()
    view.points.text = "0 0 0 0 0"
    popup = view.review_points()
    try:
        segments = popup.correspondence_image.overlay_segments
        assert ((0, 0), (2, 0)) in segments
        assert ((0, 5), (0, 0)) in segments
        assert all(0 <= x <= 24 and 0 <= y <= 18 for segment in segments for x, y in segment)
        controller.executeCommand.assert_not_called()
    finally:
        popup.dismiss(animation=False)


def test_compact_image_review_keeps_selection_image_and_close_accessible(kivy_app, tmp_path):
    from kivy.core.window import Window
    from kivy.input.motionevent import MotionEvent

    from tests.integration.conftest import set_window_viewport

    old = tuple(Window.size)
    popup = None
    try:
        set_window_viewport(500, 800)
        view, _, controller = panel()
        view.capture_reference()
        view.points.text = "0 0 0 12 9\n10 0 0 12 9"
        popup = view.review_points()
        pump_frames(8)
        image = popup.correspondence_image
        assert image.width > 100 and image.height > 100
        assert image.y >= popup.y and image.top <= popup.top

        class Touch(MotionEvent):
            def depack(self, args):
                self.sx, self.sy = args
                self.profile = ["pos"]
                super().depack(args)

        point = image.image_pixel_to_local((12, 9))
        touch = Touch("test", 1, (0, 0))
        touch.x, touch.y = point
        touch.pos = point
        assert image.on_touch_down(touch)
        assert image.selected_index == 1  # co-located origins remain individually inspectable
        pump_frames(3)
        assert popup.correspondence_selector.text == "2/2"
        close = next(item for item in popup.walk() if isinstance(item, Action) and item.text == "Close")
        assert popup.y <= close.y <= close.top <= popup.top
        popup.export_to_png(str(tmp_path / "camera-correspondence-compact.png"))
        image.focus = True
        close.trigger_action(0)
        pump_frames(15)
        assert popup.parent is None and not image.focus
        controller.executeCommand.assert_not_called()
    finally:
        if popup is not None:
            popup.dismiss(animation=False)
        set_window_viewport(*old)
