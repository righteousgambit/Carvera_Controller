import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_camera_registration import CameraRegistrationPanel
from carveracontroller.machine.observed_pose import ObservedPose
from carveracontroller.machine.webcam import WebcamClient
from tests.integration.conftest import pump_frames
from tests.unit.test_camera_calibration_file import reference


def panel():
    client = WebcamClient(start=False)
    captured = reference()
    client.frame = captured.frame
    controller = SimpleNamespace(observed_pose=None, _connection_generation=1, executeCommand=Mock())
    workspace = SimpleNamespace(
        camera_client=client,
        camera_texture=SimpleNamespace(views=[]),
        machine=SimpleNamespace(controller=controller),
        choose_profile_file=Mock(),
    )
    view = CameraRegistrationPanel(workspace)
    controller.observed_pose = ObservedPose(time.monotonic(), "Idle", (0, -100, 0), (0, 0, 0), 1, 40)
    return view, client, controller


def test_capture_freezes_exact_frame_and_pose_without_changing_live_view():
    view, client, controller = panel()
    view.capture_reference()
    assert view.reference.frame is client.frame
    assert view.reference.machine_mm == (0, -100, 0)
    assert view.reference_texture.texture is not None
    assert "exposure synchronization unqualified" in view.reference_note.text
    frozen = view.reference.frame
    client.frame = None
    assert view.reference.frame is frozen
    assert view.registration is None
    controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("change", ["points", "camera", "connection"])
def test_fit_rejects_late_result_when_inputs_or_owner_change(monkeypatch, change):
    view, client, controller = panel()
    view.capture_reference()
    view.focal.text = "20 20 12 9"
    view.points.text = "0 0 0 12 9"
    workers = []
    monkeypatch.setattr(
        "carveracontroller.desktop_camera_registration.threading.Thread",
        lambda target, **kwargs: SimpleNamespace(start=lambda: workers.append(target)),
    )
    fake = SimpleNamespace(registration=object(), rms_px=0, max_px=0, outlier_indices=[], warnings=[])
    monkeypatch.setattr("carveracontroller.desktop_camera_registration.fit_camera_pose", lambda *_: fake)
    view.fit()
    assert view.running and len(workers) == 1
    if change == "points":
        view.points.text += "\n1 1 0 13 10"
    elif change == "camera":
        client.configure("http://localhost:18091/changed.jpg")
    else:
        controller._connection_generation += 1
    workers[0]()
    pump_frames(2)
    assert not view.running and view.registration is None
    assert "Fit discarded" in view.note.text
    controller.executeCommand.assert_not_called()


def test_fit_requires_reference_and_save_requires_unchanged_inputs():
    view, _, controller = panel()
    view.fit()
    assert "Capture a reference" in view.note.text
    view.registration = object()
    view.save()
    assert "Refit before saving" in view.note.text
    view.workspace.choose_profile_file.assert_not_called()
    controller.executeCommand.assert_not_called()


def test_point_pick_uses_frozen_pixels_and_requires_known_coordinates():
    view, _, controller = panel()
    view.capture_reference()
    view.reference_view.size = (240, 180)
    view.reference_view.pos = (0, 0)
    touch = SimpleNamespace(pos=(120, 90))
    view.toggle_point_pick()
    assert view._pick_reference(view.reference_view, touch)
    assert not view.points.text and "three finite" in view.note.text
    view.world_point.text = "10 20 0"
    assert view._pick_reference(view.reference_view, touch)
    assert [float(v) for v in view.points.text.split()] == [10, 20, 0, 12, 9]
    assert not view.picking_reference
    assert len(view.reference_view.overlay_segments) == 2
    controller.executeCommand.assert_not_called()


def test_zoomed_reference_pick_retains_source_pixels():
    view, _, controller = panel()
    view.capture_reference()
    view.reference_view.size = (240, 180)
    view.reference_view.pos = (0, 0)
    view.reference_view.zoom_by(2)
    view.world_point.text = "10 20 30"
    view.toggle_point_pick()
    assert not view._pick_reference(view.reference_view, SimpleNamespace(pos=(241, 90)))
    assert view.picking_reference and not view.points.text
    assert view._pick_reference(view.reference_view, SimpleNamespace(pos=(180, 90)))
    assert [float(value) for value in view.points.text.split()] == [10, 20, 30, 15, 9]
    view.undo_point_pick()
    assert not view.points.text
    controller.executeCommand.assert_not_called()


def test_reference_pick_consumes_touch_before_pan_and_navigation_preserves_points():
    from kivy.core.window import Window
    from kivy.tests.common import UnitTestTouch

    view, _, controller = panel()
    view.capture_reference()
    image = view.reference_view
    image.size = (240, 180)
    image.pos = (0, 0)
    image.zoom_by(2)
    view.world_point.text = "10 20 30"
    view.toggle_point_pick()
    pick = UnitTestTouch(180, 90)
    pick.scale_for_screen(Window.width, Window.height)
    pick.button = "left"
    assert image.on_touch_down(pick)
    assert image._drag_touch is None
    assert [float(value) for value in view.points.text.split()] == [10, 20, 30, 15, 9]
    retained = view.points.text
    drag = UnitTestTouch(120, 90)
    drag.scale_for_screen(Window.width, Window.height)
    drag.button = "left"
    assert image.on_touch_down(drag)
    assert image._drag_touch is drag
    drag.move({"x": 150 / Window.width, "y": 90 / Window.height})
    drag.scale_for_screen(Window.width, Window.height)
    assert image.on_touch_move(drag)
    assert image.frame_center[0] < 0.5
    assert image.on_touch_up(drag)
    assert image._drag_touch is None and view.points.text == retained
    wheel = UnitTestTouch(150, 90)
    wheel.scale_for_screen(Window.width, Window.height)
    wheel.button = "scrollup"
    wheel.profile.append("button")
    view.toggle_point_pick()
    zoom = image.zoom
    assert image.on_touch_down(wheel)
    assert image.zoom > zoom and view.picking_reference
    assert view.points.text == retained
    image.reset_framing()
    assert image.zoom == 1 and view.points.text == retained
    image.focus = True
    view.select_section("Fit & exchange")
    assert not image.focus
    controller.executeCommand.assert_not_called()


def test_reference_review_shows_coverage_heights_and_invalidates_residuals():
    from carveracontroller.machine.camera_registration import CameraIntrinsics, CameraPose, CameraRegistration

    view, _, controller = panel()
    view.capture_reference()
    view.points.text = "0 0 0 4 4\n1 0 0 20 4\n1 1 0 20 14\n0 1 0 4 14"
    view._refresh_review()
    assert "37.0%" in view.coverage_note.text
    assert "raised stock needs separate" in view.coverage_note.text
    assert len(view.reference_view.overlay_segments) == 12
    view.registration = CameraRegistration(CameraIntrinsics(24, 18, 20, 20, 12, 9), CameraPose((0, 0, 0), (0, 0, 100)))
    view.fit_identity = view._input_identity()
    view._refresh_review()
    assert "inspect" in view.residual_review.text and "1 ·" in view.residual_review.text
    view.points.text += "\n0 0 20 12 9"
    assert "Z 0 to 20" in view.coverage_note.text
    assert "Fit the current inputs" in view.residual_review.text
    view.points.text += "\n0 0 0 nan 9"
    assert "Line 6" in view.coverage_note.text
    assert not view.reference_view.overlay_segments
    controller.executeCommand.assert_not_called()


def test_async_load_rejects_changed_profile_and_preserves_current_registration(monkeypatch):
    view, _, _ = panel()
    view.workspace.selected_machine_profile = {"id": "first"}
    workers = []
    monkeypatch.setattr(
        "carveracontroller.desktop_camera_registration.threading.Thread",
        lambda target, **kwargs: SimpleNamespace(start=lambda: workers.append(target)),
    )
    previous = object()
    view.registration = previous
    applied = Mock()
    view._background(lambda: "loaded", applied)
    view.workspace.selected_machine_profile = {"id": "other"}
    workers[0]()
    pump_frames(2)
    applied.assert_not_called()
    assert view.registration is previous and not view.running


def test_capture_refuses_historical_camera_without_replacing_reference():
    view, _, controller = panel()
    view.capture_reference()
    captured = view.reference
    view.workspace.run_recording_panel = SimpleNamespace(camera_replay_enabled=True)
    view.capture_reference()
    assert view.reference is captured
    assert "Show live camera" in view.note.text
    controller.executeCommand.assert_not_called()


def test_repeated_frame_sequence_replaces_reference_texture():
    view, client, _ = panel()
    view.capture_reference()
    original_texture = view.reference_texture.texture
    view.reference = reference()  # Imported sources can reuse a sequence number.
    view._show_reference()
    assert view.reference_texture.texture is not original_texture
    assert view.reference_view.texture is view.reference_texture.texture


def test_job_restore_replaces_reference_and_legacy_or_empty_jobs_clear_prior_image():
    from carveracontroller.machine.camera_calibration_file import decode_calibration
    from tests.unit.test_camera_calibration_file import data

    view, _, controller = panel()
    view.capture_reference()
    result = decode_calibration(data())
    view.apply_calibration(result)
    assert view.reference is result[2] and view.fit_identity == view._input_identity()
    legacy = (result[0], result[1], None, result[3])
    view.apply_calibration(legacy)
    assert view.reference is None and view.reference_view.texture is None
    assert "legacy" in view.note.text
    view.apply_calibration(None)
    assert view.registration is None and not view.points.text and not view.focal.text
    assert view.reference_view.texture is None
    controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("width", [360, 650])
def test_camera_sections_preserve_reference_and_edits_and_release_hidden_focus(width):
    view, client, controller = panel()
    view.size_hint = (None, None)
    view.size = (width, 620)
    view.capture_reference()
    captured = view.reference
    view.world_point.text = "10 20 30"
    view.world_point.focus = True
    view.section_buttons["Fit & exchange"].dispatch("on_release")
    pump_frames(4)
    assert not view.world_point.focus
    view.points.text = "10 20 30 5 6"
    view.focal.text = "20 20 16 12"
    view.section_buttons["Reference"].dispatch("on_release")
    pump_frames(4)
    assert view.reference is captured and client.frame is captured.frame
    assert view.points.text == "10 20 30 5 6"
    assert view.world_point.text == "10 20 30"
    assert view.focal.text == "20 20 16 12"
    assert view.note.parent is view  # Results remain visible in either section.
    assert view.reference_view.width <= width
    controller.executeCommand.assert_not_called()


def test_camera_palette_opens_sections_without_configuring_or_actuating(kivy_app, monkeypatch):
    from carveracontroller.desktop_commands import workspace_commands

    workspace = kivy_app.root.desktop_workspace
    monkeypatch.setattr(workspace.machine.controller, "executeCommand", Mock())
    monkeypatch.setattr(workspace.camera_client, "configure", Mock())
    commands = {command.id: command for command in workspace_commands(workspace)}
    panel = workspace.camera_registration_panel
    for identifier, section in (("source", "Source"), ("reference", "Reference"), ("calibration", "Fit & exchange")):
        assert commands[f"camera.{identifier}"].invoke()
        assert workspace.inspector_pages.current == "Camera"
        assert panel.sections.current == section
    workspace.camera_client.configure.assert_not_called()
    workspace.machine.controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("width", [360, 650])
def test_reference_image_keeps_useful_size_and_controls_precede_image(width):
    from kivy.metrics import dp

    view, _, controller = panel()
    view.size_hint = (None, None)
    view.size = (dp(width), dp(620))
    view.capture_reference()
    pump_frames(8)
    assert dp(180) <= view.reference_view.height <= dp(420)
    primary = sum(control.height for control in view._reference_primary_controls)
    assert view.reference_view.height + primary + 3 * view._reference_content.spacing <= view.sections.height + 1
    children = view._reference_content.children
    assert children.index(view.pick_button.parent) > children.index(view.reference_view)
    assert children.index(view.world_point) > children.index(view.reference_view)
    view.reference_view.zoom_by(2)
    assert view.reference_view.zoom == 2
    view.capture_reference()
    assert view.reference_view.zoom == 1
    controller.executeCommand.assert_not_called()


def test_point_pick_undo_retains_manual_edits_and_reference_identity():
    view, _, controller = panel()
    view.capture_reference()
    view.reference_view.size = (240, 180)
    view.reference_view.pos = (0, 0)
    view.points.text = "1 2 3 4 5"
    view.world_point.text = "10 20 0"
    view.toggle_point_pick()
    assert not view._pick_reference(view.reference_view, SimpleNamespace(pos=(120, 90), button="scrollup"))
    assert not view._pick_reference(view.reference_view, SimpleNamespace(pos=(120, 90), button="right"))
    assert view.picking_reference
    assert view._pick_reference(view.reference_view, SimpleNamespace(pos=(120, 90)))
    assert not view.undo_pick_button.disabled
    view.undo_point_pick()
    assert view.points.text == "1 2 3 4 5"
    view.toggle_point_pick()
    view._pick_reference(view.reference_view, SimpleNamespace(pos=(120, 90)))
    view.points.text += "\n2 3 4 5 6"
    retained = view.points.text
    assert view.undo_pick_button.disabled
    view.undo_point_pick()
    assert view.points.text == retained
    view.capture_reference()
    assert view._pick_undo is None and view.undo_pick_button.disabled
    controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("width", [360, 650])
def test_calibration_review_tracks_reference_edits_and_save_readiness(width):
    from carveracontroller.machine.camera_calibration_file import decode_calibration
    from tests.unit.test_camera_calibration_file import data

    view, _, controller = panel()
    view.size_hint = (None, None)
    view.size = (width, 620)
    assert "No reference image" in view.review_note.text and view.save_button.disabled
    loaded = decode_calibration(data())
    view.apply_calibration(loaded)
    view.select_section("Fit & exchange")
    pump_frames(4)
    assert "Frame 7" in view.review_note.text and "1/128" in view.review_note.text
    assert "Current registration" in view.review_note.text and not view.save_button.disabled
    assert view.review_note.parent is view.points.parent
    # Kivy children are reverse visual order. Detail follows the action row.
    fitting = view.points.parent
    assert fitting.children.index(view.residual_review) < fitting.children.index(view.save_button.parent)
    view.focal.text += " "
    assert view.save_button.disabled and "refit before saving" in view.review_note.text
    view.focal.text = "20 20 12 9"
    assert not view.save_button.disabled
    view.points.text += "\n1 2 3 4 5"
    assert "2/128" in view.review_note.text and view.save_button.disabled
    view.select_section("Reference")
    view.select_section("Fit & exchange")
    assert "Inputs changed" in view.review_note.text and view.save_button.disabled
    view.apply_calibration(None)
    assert "No reference image" in view.review_note.text and "0/128" in view.review_note.text
    assert view.save_button.disabled
    controller.executeCommand.assert_not_called()


def test_rejected_calibration_import_preserves_reviewed_image_points_and_registration(tmp_path, monkeypatch):
    import json

    from carveracontroller.machine.camera_calibration_file import decode_calibration
    from tests.unit.test_camera_calibration_file import data

    view, _, controller = panel()
    view.apply_calibration(decode_calibration(data()))
    retained = (view.reference, view.registration, view.points.text, view.fit_identity)
    broken = data()
    broken["reference"]["captured_at"] = True
    path = tmp_path / "bad-timestamp.cvcal"
    path.write_text(json.dumps(broken))
    view.workspace.choose_asset_file = lambda selected, **kwargs: selected(path)
    workers = []
    monkeypatch.setattr(
        "carveracontroller.desktop_camera_registration.threading.Thread",
        lambda target, **kwargs: SimpleNamespace(start=lambda: workers.append(target)),
    )
    view.load()
    assert view.running and view.save_button.disabled
    assert "operation in progress" in view.review_note.text
    workers[0]()
    pump_frames(3)
    assert not view.running and not view.save_button.disabled
    assert "failed" in view.note.text and "timestamp" in view.note.text
    assert (view.reference, view.registration, view.points.text, view.fit_identity) == retained
    assert "Current registration" in view.review_note.text
    controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("change", ["points", "camera", "connection", "registration"])
def test_calibration_save_rechecks_review_after_file_picker(monkeypatch, change, tmp_path):
    view, client, controller = panel()
    view.capture_reference()
    view.registration = object()
    view.fit_identity = view._input_identity()
    background = Mock()
    monkeypatch.setattr(view, "_background", background)
    view.save()
    selected = view.workspace.choose_profile_file.call_args.args[0]
    if change == "points":
        view.points.text = "0 0 0 1 1"
    elif change == "camera":
        client.configure("http://127.0.0.1:18091/other.jpg")
    elif change == "connection":
        controller._connection_generation += 1
    else:
        view.registration = object()
    destination = tmp_path / "calibration.cvcal"
    selected(destination)
    background.assert_not_called()
    assert not destination.exists()
    assert "No file written" in view.note.text
    controller.executeCommand.assert_not_called()


def test_unchanged_calibration_picker_starts_export(monkeypatch, tmp_path):
    view, _client, controller = panel()
    view.capture_reference()
    view.registration = object()
    view.fit_identity = view._input_identity()
    background = Mock()
    monkeypatch.setattr(view, "_background", background)
    view.save()
    selected = view.workspace.choose_profile_file.call_args.args[0]
    selected(tmp_path / "calibration.cvcal")
    background.assert_called_once()
    assert callable(background.call_args.args[0])
    controller.executeCommand.assert_not_called()


def test_nested_reference_scroll_routes_image_gestures_before_content_scrolling():
    from kivy.core.window import Window
    from kivy.tests.common import UnitTestTouch
    from kivy.uix.floatlayout import FloatLayout

    from carveracontroller.desktop_components import DesktopScrollView

    view, _, controller = panel()
    view.capture_reference()
    view.select_section("Reference")
    image = view.reference_view
    image.parent.remove_widget(image)
    image.size_hint = (None, None)
    image.size, image.pos = (500, 300), (20, 450)
    inner_content = FloatLayout(size_hint_y=None, height=800)
    inner_content.add_widget(image)
    inner = DesktopScrollView(size_hint=(None, None), size=(580, 600), pos=(0, 200), do_scroll_x=False)
    inner.add_widget(inner_content)
    content = FloatLayout(size_hint_y=None, height=900)
    content.add_widget(inner)
    outer = DesktopScrollView(size_hint=(None, None), size=(600, 800), pos=(40, 30), do_scroll_x=False)
    outer.add_widget(content)
    Window.add_widget(outer)
    try:
        pump_frames(8)
        x, y = image.to_window(*image.center)
        assert outer.collide_point(x, y)
        before_scroll = outer.scroll_y, inner.scroll_y
        wheel = UnitTestTouch(x, y)
        wheel.scale_for_screen(Window.width, Window.height)
        wheel.profile.append("button")
        wheel.button = "scrollup"
        wheel.touch_down()
        assert image.zoom == pytest.approx(1.25)
        wheel.touch_up()
        image.zoom_by(2)
        drag = UnitTestTouch(x, y)
        drag.scale_for_screen(Window.width, Window.height)
        drag.button = "left"
        drag.touch_down()
        assert image._drag_touch is drag
        drag.touch_move(x + 30, y)
        assert image.frame_center[0] < 0.5
        drag.touch_up()
        assert image._drag_touch is None
        assert (outer.scroll_y, inner.scroll_y) == before_scroll
        assert not view.points.text
        view.world_point.text = "10 20 30"
        view.toggle_point_pick()
        pixel = image.local_to_image_pixel(image.center)
        pick = UnitTestTouch(x, y)
        pick.button = "left"
        pick.touch_down()
        assert image._drag_touch is None
        pick.touch_up()
        assert [float(v) for v in view.points.text.split()] == pytest.approx([10, 20, 30, *pixel])
        retained = view.points.text
        view.toggle_point_pick()
        wheel = UnitTestTouch(x, y)
        wheel.profile.append("button")
        wheel.button = "scrolldown"
        wheel.touch_down()
        wheel.touch_up()
        assert view.picking_reference and view.points.text == retained
        assert (outer.scroll_y, inner.scroll_y) == before_scroll
        controller.executeCommand.assert_not_called()
    finally:
        image.focus = False
        Window.remove_widget(outer)
