from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from carveracontroller.desktop_joint_feedback import JointFeedbackPanel
from carveracontroller.machine.joint_feedback import review_joint_feedback
from tests.integration.conftest import pump_frames
from tests.unit.test_joint_feedback import trace


def test_chart_midpoints_selection_metrics_and_replacement_without_machine_actions():
    panel = JointFeedbackPanel()
    review = review_joint_feedback(trace(), 6, (("axis", "linear"),))
    panel.show(review, ("program", 2))
    panel.metric.text = "Velocity"
    assert tuple(point.elapsed for point in panel.plot.trace.points) == (0.5, 2, 4.5)
    panel.select(1)
    assert "t 2 s · value 4 mm/s" in panel.note.text
    panel.metric.text = "Signed error"
    assert panel.cursor == 0
    assert panel.plot.trace.points[0].values == (0.25,)
    panel.show(review_joint_feedback(trace((0, 6), commands=False), 6, (("axis", "rotary"),)), ("other", 3))
    assert panel.metric.text == "Reported position"
    panel.metric.text = "Jerk"
    assert panel.plot.trace.points == () and "No samples" in panel.note.text
    panel.show(None, None)
    assert panel.plot.trace.points == () and panel.next.disabled


def test_chart_pages_retain_all_samples_and_time_based_nearest_selection():
    panel = JointFeedbackPanel()
    record = trace(tuple(range(501)))
    panel.show(review_joint_feedback(record, 500, (("axis", "linear"),)), ("p", 2))
    assert len(panel.plot.trace.points) == 200
    panel.next.dispatch("on_release")
    assert panel.cursor == 200 and panel.plot.trace.points[0].sample == 200
    panel.next.dispatch("on_release")
    assert len(panel.plot.trace.points) == 101 and panel.next.disabled
    panel.plot.pos = (0, 0)
    panel.plot.size = (224, 170)
    touch = SimpleNamespace(pos=(112, 80), x=112)
    assert panel.plot.on_touch_down(touch)
    assert panel.cursor == 450
    for button in ("scrollup", "scrolldown", "right"):
        assert not panel.plot.on_touch_down(SimpleNamespace(pos=(112, 80), x=112, button=button))
        assert panel.cursor == 450
    panel.select(9999)
    assert panel.cursor == 500


@pytest.mark.parametrize("width", [360, 650])
def test_feedback_chart_responsive_readable_and_keyboard_point_actions(width, tmp_path):
    from kivy.uix.popup import Popup
    from kivy.uix.scrollview import ScrollView

    panel = JointFeedbackPanel()
    panel.show(review_joint_feedback(trace(), 6, (("axis", "linear"),)), ("p", 2))
    scroll = ScrollView(do_scroll_x=False)
    scroll.add_widget(panel)
    popup = Popup(content=scroll, size_hint=(None, None), size=(width, 650))
    popup.open(animation=False)
    try:
        pump_frames(6)
        assert panel.plot.width <= scroll.width
        assert panel.note.texture_size[1] <= panel.note.height
        assert panel.joint.right <= panel.right and panel.metric.right <= panel.right
        scroll.export_to_png(str(tmp_path / f"feedback-chart-{width}.png"))
    finally:
        popup.dismiss(animation=False)


def test_window_wheel_and_keyboard_route_over_chart_without_changing_block():
    from kivy.base import EventLoop
    from kivy.core.window import Window
    from kivy.input.providers.mouse import MouseMotionEventProvider
    from kivy.uix.popup import Popup

    from carveracontroller.desktop_components import DesktopScrollView
    from tests.integration.test_stage_pointer_routing import system_position

    panel = JointFeedbackPanel()
    panel.show(review_joint_feedback(trace(tuple(range(501))), 500, (("axis", "linear"),)), ("program", 3))
    scroll = DesktopScrollView(do_scroll_x=False)
    scroll.add_widget(panel)
    popup = Popup(content=scroll, size_hint=(None, None), size=(650, 400))
    provider = MouseMotionEventProvider("feedback-navigation", "multitouch_on_demand")
    popup.open(animation=False)
    try:
        pump_frames(8)
        scroll.scroll_y = 0.5
        pump_frames(5)
        position = system_position(panel.plot.to_window(*panel.plot.center))
        provider.start()
        for button, direction in (("scrolldown", 1), ("scrollup", -1)):
            before = scroll.scroll_y
            Window.dispatch("on_mouse_down", *position, button, [])
            provider.update(EventLoop.post_dispatch_input)
            Window.dispatch("on_mouse_up", *position, button, [])
            provider.update(EventLoop.post_dispatch_input)
            pump_frames(5)
            assert scroll.scroll_y - before == pytest.approx(
                direction * scroll.scroll_wheel_distance / (panel.height - scroll.height)
            )
            assert panel.cursor == 0 and panel.identity == ("program", 3)
        Window.dispatch("on_mouse_down", *position, "left", [])
        provider.update(EventLoop.post_dispatch_input)
        Window.dispatch("on_mouse_up", *position, "left", [])
        provider.update(EventLoop.post_dispatch_input)
        pump_frames(3)
        assert panel.plot.focus
        keyboard = panel.plot._keyboard
        for key, expected in (
            ("home", 0),
            ("right", 1),
            ("pagedown", 201),
            ("end", 500),
            ("left", 499),
            ("pageup", 299),
            ("home", 0),
            ("left", 0),
        ):
            keyboard.dispatch("on_key_down", (0, key), "", [])
            assert panel.cursor == expected and panel.identity == ("program", 3)
        keyboard.dispatch("on_key_down", (275, "right"), "", ["super"])
        assert panel.cursor == 0
        panel.show(None, None)
        assert not panel.plot.focus
    finally:
        panel.plot.focus = False
        provider.stop()
        popup.dismiss(animation=False)
