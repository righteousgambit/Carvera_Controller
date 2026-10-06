from kivy.clock import Clock
from kivy.core.window import Window
from kivy.tests.common import UnitTestTouch
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import DesktopScrollView


def test_wheel_moves_content_and_bar_drag_is_enabled():
    view = DesktopScrollView(size=(400, 300), size_hint=(None, None), do_scroll_x=False)
    host = BoxLayout(size=(400, 300), size_hint=(None, None))
    host.add_widget(view)
    content = BoxLayout(size_hint_y=None, height=1200)
    view.add_widget(content)
    for _ in range(5):
        Clock.tick()
    assert view.scroll_type == ["content", "bars"]
    touch = UnitTestTouch(view.center_x, view.center_y)
    touch.scale_for_screen(Window.width, Window.height)
    touch.profile.append("button")
    touch.button = "scrollup"
    assert view.on_scroll_start(touch)
    for _ in range(5):
        Clock.tick()
    assert view.scroll_y < 1
    view.scroll_y = 1
    touch = UnitTestTouch(view.right - view.bar_width / 2, view.top - 20)
    touch.scale_for_screen(Window.width, Window.height)
    assert view.on_scroll_start(touch)
    assert touch.ud["in_bar_y"]
    previous = view.scroll_y
    touch.dispatch_done()
    touch.move({"x": touch.sx, "y": (view.top - 120) / (Window.height - 1)})
    touch.scale_for_screen(Window.width, Window.height)
    touch.grab_current = view
    view.on_touch_move(touch)
    assert view.scroll_y < previous


def test_nested_wheel_moves_inner_then_bubbles_at_its_boundary():
    outer = DesktopScrollView(size=(400, 300), size_hint=(None, None), do_scroll_x=False)
    content = BoxLayout(orientation="vertical", size_hint_y=None, height=900)
    inner = DesktopScrollView(size_hint_y=None, height=200, do_scroll_x=False)
    inner.add_widget(BoxLayout(size_hint_y=None, height=600))
    content.add_widget(inner)
    content.add_widget(BoxLayout(size_hint_y=None, height=700))
    outer.add_widget(content)
    for _ in range(5):
        Clock.tick()

    def wheel():
        x, y = inner.to_window(*inner.center)
        touch = UnitTestTouch(x, y)
        touch.scale_for_screen(Window.width, Window.height)
        touch.profile.append("button")
        touch.button = "scrollup"
        assert outer.on_scroll_start(touch)
        for _ in range(5):
            Clock.tick()

    wheel()
    assert inner.scroll_y < 1
    assert outer.scroll_y == 1
    inner.scroll_y = 0
    for _ in range(5):
        Clock.tick()
    wheel()
    assert inner.scroll_y == 0
    assert outer.scroll_y < 1


def test_scrollbar_moves_immediately_below_content_drag_threshold():
    view = DesktopScrollView(size=(400, 300), size_hint=(None, None), do_scroll_x=False)
    view.add_widget(BoxLayout(size_hint_y=None, height=340))
    for _ in range(5):
        Clock.tick()
    touch = UnitTestTouch(view.right - view.bar_width / 2, view.top - 20)
    touch.scale_for_screen(Window.width, Window.height)
    touch.profile.append("button")
    touch.button = "left"
    assert view.on_scroll_start(touch)
    assert touch.ud["in_bar_y"]
    previous = view.scroll_y
    touch.dispatch_done()
    touch.move({"x": touch.sx, "y": (view.top - 22) / (Window.height - 1)})
    touch.scale_for_screen(Window.width, Window.height)
    touch.grab_current = view
    view.on_touch_move(touch)
    assert view.scroll_y < previous


def test_content_pan_keeps_threshold_and_disabled_bar_does_not_capture():
    view = DesktopScrollView(size=(400, 300), size_hint=(None, None), do_scroll_x=False)
    view.add_widget(BoxLayout(size_hint_y=None, height=600))
    for _ in range(5):
        Clock.tick()
    touch = UnitTestTouch(view.center_x, view.center_y)
    touch.scale_for_screen(Window.width, Window.height)
    assert view.on_scroll_start(touch)
    assert touch.ud[view._get_uid()]["mode"] == "unknown"
    view.disabled = True
    bar = UnitTestTouch(view.right - view.bar_width / 2, view.top - 20)
    bar.scale_for_screen(Window.width, Window.height)
    assert view.on_scroll_start(bar)
    assert view._get_uid() not in bar.ud
    assert view.scroll_y == 1
