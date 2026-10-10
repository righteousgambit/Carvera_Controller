import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from kivy.core.window import Window
from kivy.metrics import dp

from carveracontroller.desktop_components import Field
from tests.integration.conftest import pump_frames, set_window_viewport
from tests.integration.test_camera_reference import panel
from tests.integration.touch_input import WindowTouch
from tests.unit.test_camera_lens_study import study


def measured_panel():
    view, client, controller = panel()
    measured = study()
    source = client.calibration_snapshot()[3]
    captures = tuple(
        replace(capture, reference=replace(capture.reference, source_sha256=source, camera_generation=0))
        for capture in measured.captures
    )
    measured = replace(measured, captures=captures)
    view.reference = captures[0].reference
    view.reference_revision += 1
    view.focal.text = "19 20 12 9"
    view.lens_study._set_study(measured)
    view.lens_study.distortion_choice.text = "Keep prior distortion"
    return view, client, controller, measured


def wait_complete(view):
    deadline = time.monotonic() + 15
    while view.running and time.monotonic() < deadline:
        pump_frames(1)
        time.sleep(0.005)
    assert not view.running, "Owned calibration worker did not stop"
    pump_frames(2)


def test_real_solver_applies_full_precision_lens_and_invalidates_bed_fit_without_commands():
    view, _, controller, measured = measured_panel()
    lens = view.lens_study
    view.registration = object()
    view.fit_identity = view._input_identity()
    view._refresh_review()
    assert not view.save_button.disabled
    lens.fit()
    wait_complete(view)
    assert lens._current() and not lens.apply_button.disabled
    assert "RMS" in lens.detail.text and "coverage" in lens.detail.text
    assert lens.result[0].fx == pytest.approx(20, abs=0.001)
    assert lens.study.prior == measured.prior
    lens.apply()
    assert float(view.focal.text.split()[0]) == lens.result[0].fx
    assert view.lens_model_size == (24, 18) and view.lens_model_source == measured.source_sha256
    assert view.save_button.disabled and view.fit_identity != view._input_identity()
    assert "Refit bed registration" in view.note.text
    assert view.reference_for_lens
    identity = view._input_identity()
    view.fit()
    assert not view.running and "lens-study target reference" in view.note.text
    assert view._input_identity() == identity
    popup = lens.review_selected()
    try:
        assert popup is not None
        assert lens.study == measured
    finally:
        popup.dismiss()
    from carveracontroller.machine.camera_calibration_file import decode_calibration
    from tests.unit.test_camera_calibration_file import data

    view.apply_calibration(decode_calibration(data()))
    assert not view.reference_for_lens and not view.save_button.disabled
    view.reference_for_lens = True
    view.capture_reference()
    assert not view.reference_for_lens
    controller.executeCommand.assert_not_called()


def test_capture_custody_duplicate_rejection_removal_and_prior_update():
    view, _, controller, measured = measured_panel()
    lens = view.lens_study
    lens._set_study(None)
    view.points.text = "\n".join(
        " ".join(repr(v) for v in (*o.world_mm, *o.pixel)) for o in measured.captures[0].observations
    )
    lens.add_reference()
    assert lens.study.captures == measured.captures[:1]
    assert view.reference_for_lens
    view.fit()
    assert not view.running and "bed-frame" in view.note.text
    before = lens.study
    lens.add_reference()
    assert lens.study is before and "already" in view.note.text
    view.points.text = "changed current draft"
    assert lens.study.captures[0].observations == measured.captures[0].observations
    view.focal.text = "20 21 12 9"
    lens.use_prior()
    assert lens.study.prior.fx == 20
    lens.remove_selected()
    assert lens.study is None and lens.capture_choice.text == "No views"
    controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("action", ["cancel", "source", "inputs", "detach"])
def test_owned_worker_cancel_or_stale_result_retains_measurements_and_never_replaces_worker(monkeypatch, action):
    view, client, controller, measured = measured_panel()
    lens = view.lens_study
    entered, release = threading.Event(), threading.Event()
    original = __import__("carveracontroller.desktop_camera_lens_study", fromlist=["calibrate_camera"]).calibrate_camera
    workers = []

    def controlled(*args, **kwargs):
        workers.append(threading.current_thread().name)
        entered.set()
        assert release.wait(5)
        return original(*args, **kwargs)

    monkeypatch.setattr("carveracontroller.desktop_camera_lens_study.calibrate_camera", controlled)
    lens.fit()
    assert entered.wait(2)
    lens.fit()
    assert len(workers) == 1 and view.running
    if action == "cancel":
        lens.cancel()
        assert view.running and lens.cancel_event.is_set()
    elif action == "source":
        client.configure("http://localhost:18091/other-camera.jpg")
    elif action == "inputs":
        view.focal.text = "22 23 12 9"
    else:
        lens.dispose()
        assert view.running and lens.cancel_event.is_set()
    release.set()
    wait_complete(view)
    assert lens.result is None and lens.study == measured
    assert lens.cancel_event is None and len(workers) == 1
    if action != "detach":
        assert "cancelled" in view.note.text or "withheld" in view.note.text
    controller.executeCommand.assert_not_called()


def test_async_file_picker_rechecks_owner_and_roundtrips_exact_measurements(tmp_path):
    view, _, controller, measured = measured_panel()
    lens = view.lens_study
    path = tmp_path / "measurement.cvlens"
    lens.save()
    selected = view.workspace.choose_profile_file.call_args.args[0]
    controller._connection_generation += 1
    selected(str(path))
    assert not path.exists() and "owner changed" in view.note.text
    lens.save()
    selected = view.workspace.choose_profile_file.call_args.args[0]
    selected(str(path))
    wait_complete(view)
    assert path.exists() and "read back" in view.note.text
    lens._set_study(None)
    lens.load()
    view.workspace.choose_profile_file.call_args.args[0](str(path))
    wait_complete(view)
    assert lens.study == measured and lens.result is None
    assert "no cached fit trusted" in view.note.text
    controller.executeCommand.assert_not_called()


def test_solver_failure_and_thread_start_refusal_release_ownership_without_losing_evidence(monkeypatch):
    view, _, controller, measured = measured_panel()
    lens = view.lens_study

    def refuse_solver(*_args, **_kwargs):
        raise ValueError("Calibration views need distinctly different board tilts")

    monkeypatch.setattr("carveracontroller.desktop_camera_lens_study.calibrate_camera", refuse_solver)
    lens.fit()
    wait_complete(view)
    assert lens.result is None and lens.study == measured
    assert "different board tilts" in view.note.text and lens.cancel_event is None

    def refuse_start(_thread):
        raise RuntimeError("Thread allocation refused")

    monkeypatch.setattr("carveracontroller.desktop_camera_lens_study.threading.Thread.start", refuse_start)
    lens.fit()
    assert not view.running and lens.cancel_event is None
    assert lens.study == measured and "did not start" in view.note.text
    assert not lens.fit_button.disabled and lens.cancel_button.disabled
    controller.executeCommand.assert_not_called()


@pytest.mark.parametrize("width,height", [(360, 560), (430, 560), (650, 700)])
def test_rendered_navigation_image_review_and_fit_actions_reflow(width, height, tmp_path):
    from carveracontroller.desktop_camera_registration import CameraRegistrationPanel

    view, _, controller, measured = measured_panel()
    # Include the real Source section: four controls switch to a choice rather
    # than clipping or wrapping inside the fixed-height navigation bar.
    mounted = CameraRegistrationPanel(view.workspace, source=Field(text="Camera source"))
    lens = mounted.lens_study
    mounted.reference = measured.captures[0].reference
    mounted.focal.text = "19 20 12 9"
    lens._set_study(measured)
    lens.distortion_choice.text = "Keep prior distortion"
    before = Window.system_size
    try:
        set_window_viewport(dp(width), dp(height))
        Window.add_widget(mounted)
        pump_frames(8)
        mounted.select_section("Lens study")
        pump_frames(4)
        if width < 438:
            assert mounted.section_choice.parent is mounted.section_navigation
        else:
            assert mounted.section_tabs.parent is mounted.section_navigation
            button = mounted.section_buttons["Lens study"]
            assert mounted.collide_point(*button.center)
            touch = WindowTouch(*button.center)
            touch.touch_down()
            touch.touch_up()
            pump_frames(2)
        scroll = mounted.sections.current_screen.children[0]
        scroll.scroll_y = 0
        pump_frames(6)
        fit = lens.fit_button
        assert scroll.collide_point(*fit.to_window(fit.center_x, fit.center_y))
        # Kivy layouts use their parent's coordinate system; button.center is
        # transformed through the scroll content before entering Window input.
        touch = WindowTouch(*fit.to_window(*fit.center))
        touch.touch_down()
        touch.touch_up()
        wait_complete(mounted)
        assert lens._current()
        pump_frames(8, sleep=0.01)
        assert fit.width >= 120
        actual = Window.screenshot(name=str(tmp_path / f"lens-study-{width}.png"))
        assert actual and Path(actual).stat().st_size > 1000
        controller.executeCommand.assert_not_called()
    finally:
        Window.remove_widget(mounted)
        Window.system_size = before
        pump_frames(4)
