import threading
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_program_picker import ProgramBrowser, ProgramEntry
from tests.integration.conftest import pump_frames


def wait_for_inspection(browser):
    for _ in range(40):
        pump_frames(2)
        if browser.inspection is not None:
            return
    raise AssertionError("Inspection did not finish")


def test_picker_shows_captured_geometry_and_missing_preview_tools_without_transfer(kivy_app, tmp_path, monkeypatch):
    ws = kivy_app.root.desktop_workspace
    send, upload = Mock(), Mock()
    monkeypatch.setattr(ws.machine.controller, "executeCommand", send)
    monkeypatch.setattr(ws.machine, "check_and_upload", upload)
    file = tmp_path / "fixture.nc"
    file.write_text("G21 G90 G17 G94 G54\nT99 M6\nG0 X0 Y0 Z2\n(Operation: Face)\nG1 Z0 F100\nG1 X8\n")
    browser = ProgramBrowser(ws)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        browser.select(browser.entries[0])
        wait_for_inspection(browser)
        assert "G21" in browser.metadata.text
        assert "Missing preview definitions: T99" in browser.excerpt.text
        assert "Face" in browser.excerpt.text
        pump_frames(3)
        assert browser.excerpt.cursor == (0, 0)
        assert browser.excerpt.scroll_y == 0
        assert browser.thumbnail.segments
        assert "geometry incomplete" in browser.inspection_note.text
        assert browser.rows.children[0].valign == "middle"
        browser.popup.export_to_png(str(tmp_path / "program-inspection.png"))
        send.assert_not_called()
        upload.assert_not_called()
    finally:
        browser.dismiss()


def test_slow_old_file_cannot_replace_new_selection_or_closed_picker(kivy_app, tmp_path, monkeypatch):
    from carveracontroller.machine import program_preview

    first, second = tmp_path / "first.nc", tmp_path / "second.nc"
    first.write_text("G21\nT1\n")
    second.write_text("G20\nT2\n")
    release, entered = threading.Event(), threading.Event()
    original = program_preview.inspect_program

    def controlled(path):
        if path == str(first):
            entered.set()
            release.wait(5)
        return original(path)

    monkeypatch.setattr(program_preview, "inspect_program", controlled)
    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        browser.select(ProgramEntry(first.name, str(first), False))
        for _ in range(20):
            pump_frames(2)
            if entered.is_set():
                break
        assert entered.is_set()
        browser.select(ProgramEntry(second.name, str(second), False))
        wait_for_inspection(browser)
        assert browser.inspection.tool_ids == (2,)
        release.set()
        pump_frames(20)
        assert browser.inspection.tool_ids == (2,)
        browser.select(ProgramEntry(first.name, str(first), False))
        browser.dismiss()
        previous = browser.excerpt.text
        pump_frames(20)
        assert browser.excerpt.text == previous
    finally:
        release.set()
        browser.dismiss()


def test_multi_frame_thumbnail_does_not_overlay_unregistered_frames(kivy_app, tmp_path):
    file = tmp_path / "frames.nc"
    file.write_text("G21 G90 G17 G94 G54\nG0 X0 Y0 Z1\nG1 X1 F100\nG55\nG1 X2\n")
    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        browser.select(browser.entries[0])
        wait_for_inspection(browser)
        assert not browser.thumbnail.segments
        assert "Multiple work frames" in browser.inspection_note.text
    finally:
        browser.dismiss()


def test_program_picker_stacks_inspection_at_narrow_width(kivy_app, tmp_path):
    from kivy.core.window import Window
    from kivy.metrics import dp

    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        browser._resize(None, (dp(600), Window.height))
        pump_frames(10)
        assert browser.body.orientation == "vertical"
        assert browser.details.width <= browser.body.width + dp(1)
        viewport = browser.detail_content.parent
        assert browser.detail_content.height > viewport.height
        top = browser.detail_title.to_window(browser.detail_title.x, browser.detail_title.top)[1]
        assert top <= browser.details.to_window(browser.details.x, browser.details.top)[1]
        assert top >= browser.details.to_window(browser.details.x, browser.details.y)[1]
        assert browser.local_button.parent.cols == 2
        browser.popup.export_to_png(str(tmp_path / "program-picker-narrow.png"))
        browser._resize(None, (dp(1100), Window.height))
        pump_frames(10)
        assert browser.body.orientation == "horizontal"
    finally:
        browser._resize(None, Window.size)
        browser.dismiss()


def test_wheel_over_source_scrolls_complete_details_and_selection_resets(kivy_app, tmp_path):
    from kivy.core.window import Window
    from kivy.tests.common import UnitTestTouch

    file = tmp_path / "long.nc"
    file.write_text("G21 G90 G54\nT99 M6\n" + "\n".join(f"G1 X{i} Y{i % 2} F100" for i in range(50)))
    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    browser.open()
    try:
        browser.select(browser.entries[0])
        wait_for_inspection(browser)
        pump_frames(15)
        assert browser.excerpt.height >= browser.excerpt.minimum_height
        assert browser.detail_content.height > browser.detail_scroll.height
        before = browser.detail_scroll.scroll_y
        # The source occupies the bottom of the overflowing content. Scroll
        # into it, then deliver the real wheel event through the popup tree.
        browser.detail_scroll.scroll_y = 0
        pump_frames(10)
        x, y = browser.detail_scroll.to_window(*browser.detail_scroll.center)
        touch = UnitTestTouch(x, y)
        touch.scale_for_screen(Window.width, Window.height)
        touch.profile.append("button")
        touch.button = "scrolldown"
        assert browser.popup.on_touch_down(touch)
        browser.popup.on_touch_up(touch)
        pump_frames(10)
        assert browser.detail_scroll.scroll_y > 0
        assert browser.excerpt.scroll_y == 0
        browser.select(browser.entries[0])
        wait_for_inspection(browser)
        pump_frames(10)
        assert browser.detail_scroll.scroll_y == before == 1
        browser.popup.export_to_png(str(tmp_path / "single-scroll-inspection.png"))
    finally:
        browser.dismiss()


@pytest.mark.parametrize("horizontal_effect", [True, False])
def test_window_mouse_wheel_routes_over_details_in_both_directions(kivy_app, tmp_path, horizontal_effect):
    from kivy.base import EventLoop
    from kivy.core.window import Window
    from kivy.input.providers.mouse import MouseMotionEventProvider

    file = tmp_path / "wheel.nc"
    file.write_text("G21 G90 G54\nT99 M6\n" + "\n".join(f"G1 X{i} F100" for i in range(80)))
    browser = ProgramBrowser(kivy_app.root.desktop_workspace)
    browser.local_path = str(tmp_path)
    browser.open()
    # The fixture prepares the app without starting OS input providers.
    # Bind the production mouse provider to Window for this test's lifetime.
    provider = MouseMotionEventProvider("inspection-wheel", "multitouch_on_demand")
    try:
        browser.select(browser.entries[0])
        wait_for_inspection(browser)
        pump_frames(10)
        view = browser.detail_scroll
        if not horizontal_effect:
            view.effect_x = None
        view.scroll_y = 0.5
        pump_frames(5)
        x, y = view.to_window(*view.center)
        # Native Window events use top-down system coordinates; the provider
        # normalizes them and the event loop scales the resulting motion event.
        x *= Window.system_size[0] / Window.width
        y = (Window.height - y) * Window.system_size[1] / Window.height
        provider.start()
        for button, sign in (("scrolldown", 1), ("scrollup", -1)):
            before = view.scroll_y
            Window.dispatch("on_mouse_down", x, y, button, [])
            provider.update(EventLoop.post_dispatch_input)
            Window.dispatch("on_mouse_up", x, y, button, [])
            provider.update(EventLoop.post_dispatch_input)
            pump_frames(5)
            expected = sign * view.scroll_wheel_distance / (view._viewport.height - view.height)
            assert view.scroll_y - before == pytest.approx(expected)
            assert browser.excerpt.scroll_y == 0
        browser.popup.export_to_png(str(tmp_path / "window-wheel-inspection.png"))
    finally:
        provider.stop()
        browser.dismiss()


def test_orientation_cube_is_last_after_program_mesh_rebuild(kivy_app, tmp_path):
    from pathlib import Path

    from kivy.core.window import Window

    from tests.integration.conftest import load_gcode_file

    root = kivy_app.root
    viewer = root.gcode_viewer
    for length in (20, 30):
        file = tmp_path / f"cube-{length}.nc"
        file.write_text(f"G21 G90 G54\nT99 M6\nG0 X0 Y0 Z2\nG1 X{length} F600\nM30\n")
        load_gcode_file(kivy_app, str(file))
        kivy_app.selected_local_filename = str(file)
        pump_frames(10)
        assert viewer.canvas.children[-1] == viewer.viewcubemesh
        assert root.desktop_workspace._legacy_viewer_overlay.parent is None
        assert viewer.viewcubemesh["view_mat"].transform_point(0, 0, 0) == pytest.approx((0.0, 0.0, -3.0))
    # GL callbacks need the real window framebuffer, not widget FBO export.
    target = tmp_path / "orientation-cube-foreground.png"
    actual = Window.screenshot(name=str(target))
    if actual != str(target):
        Path(actual).rename(target)


def test_orientation_face_click_is_independent_of_machine_camera_center(kivy_app):
    from kivy.core.window import Window
    from kivy.tests.common import UnitTestTouch

    from carveracontroller.GcodeViewer import VIEW_CUBE_WORLD_SCALE, VIEW_FACE_PRESETS, pick_face

    root = kivy_app.root
    viewer = root.gcode_viewer
    original = (viewer.m_xLookAt, viewer.m_yLookAt, viewer.m_zLookAt, viewer.m_distance)
    try:
        for center in ((0, 0, 0), (100000, -50000, 40000)):
            viewer.m_xLookAt, viewer.m_yLookAt, viewer.m_zLookAt = center
            viewer.m_distance = 200000
            viewer.m_xRot, viewer.m_yRot = 30, 20
            viewer.update_view()
            pump_frames(3)
            expected = VIEW_FACE_PRESETS[
                pick_face(0, 0, viewer._view_matrix(3, (0, 0, 0)), viewer._view_cube_hud_proj(), VIEW_CUBE_WORLD_SCALE)
            ]
            x, y, width, height = viewer._view_cube_screen_rect()
            touch = UnitTestTouch(x + width / 2, y + height / 2)
            touch.scale_for_screen(Window.width, Window.height)
            assert root.on_touch_down(touch)
            root.on_touch_up(touch)
            assert (viewer.m_xRot, viewer.m_yRot) == expected
    finally:
        viewer.m_xLookAt, viewer.m_yLookAt, viewer.m_zLookAt, viewer.m_distance = original
        viewer.update_view()
