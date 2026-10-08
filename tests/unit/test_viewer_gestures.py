"""Pane-owned gestures must not fall through or stop at a pane boundary."""

import pytest
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.tests.common import UnitTestTouch

from carveracontroller.GcodeViewer import TOUCH_CLAIMED, GCodeViewer


@pytest.fixture
def viewer(monkeypatch):
    item = GCodeViewer()
    item.size_hint = (None, None)
    item.pos, item.size = (40, 50), (400, 300)
    monkeypatch.setattr(item, "_handle_view_cube_touch", lambda touch: False)
    yield item
    Clock.unschedule(item._on_frame_tick)


def touch_at(x, y, button="left"):
    touch = UnitTestTouch(x, y)
    touch.scale_for_screen(Window.width, Window.height)
    touch.profile.append("button")
    touch.button = button
    return touch


def move(touch, x, y, viewer):
    touch.dispatch_done()
    touch.move({"x": x / (Window.width - 1), "y": y / (Window.height - 1)})
    touch.scale_for_screen(Window.width, Window.height)
    touch.grab_current = viewer
    return viewer.on_touch_move(touch)


def test_wheel_consumed_inside_and_ignored_outside(viewer):
    initial = viewer.m_zoom
    assert viewer.on_touch_down(touch_at(200, 200, "scrollup")) is True
    assert viewer.m_zoom < initial
    after = viewer.m_zoom
    assert viewer.on_touch_down(touch_at(500, 200, "scrolldown")) is False
    assert viewer.m_zoom == after


def test_orbit_keeps_capture_outside_and_releases(viewer):
    viewer.set_orbit(True)
    touch = touch_at(200, 200)
    before = viewer.m_yRot
    assert viewer.on_touch_down(touch) is True
    assert touch.ud[TOUCH_CLAIMED] is viewer
    assert move(touch, 500, 200, viewer) is True
    assert viewer.m_yRot != before
    assert viewer.on_touch_up(touch) is True
    assert TOUCH_CLAIMED not in touch.ud
    assert not touch.grab_list


def test_pan_right_button_and_no_duplicate_normal_move(viewer):
    viewer.set_orbit(True)
    touch = touch_at(200, 200, "right")
    original = viewer.m_xPan
    viewer.on_touch_down(touch)
    touch.x += 50
    assert viewer.on_touch_move(touch) is True
    assert viewer.m_xPan == original
    touch.grab_current = viewer
    assert viewer.on_touch_move(touch) is True
    assert viewer.m_xPan == pytest.approx(original - 50 / viewer.width)
    viewer.on_touch_up(touch)


def test_disabled_and_other_viewer_claims_do_not_change_pose(viewer):
    initial = viewer.m_zoom
    viewer.disabled = True
    assert viewer.on_touch_down(touch_at(200, 200, "scrollup")) is False
    viewer.disabled = False
    touch = touch_at(200, 200)
    touch.ud[TOUCH_CLAIMED] = object()
    assert viewer.on_touch_down(touch) is False
    assert viewer.m_zoom == initial
