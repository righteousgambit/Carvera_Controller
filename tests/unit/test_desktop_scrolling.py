from kivy.clock import Clock
from kivy.core.window import Window
from kivy.tests.common import UnitTestTouch
from kivy.uix.boxlayout import BoxLayout

from carveracontroller.desktop_components import DesktopScrollView


def test_reveal_of_fitting_content_retains_position_and_disabled_axes_do_not_move():
    view = DesktopScrollView(size=(400, 300), size_hint=(None, None), do_scroll_x=False)
    host = BoxLayout(size=(400, 300), size_hint=(None, None))
    host.add_widget(view)
    content = BoxLayout(size=(400, 200), size_hint=(None, None))
    view.add_widget(content)
    for _ in range(5):
        Clock.tick()
    assert view.convert_distance_to_scroll(0, 0) == (0, 0)
    assert view.convert_distance_to_scroll(20, 20) == (0, 0)
    view.scroll_to(content, animate=False)
    assert view.scroll_y == 1
    content.height = 600
    for _ in range(5):
        Clock.tick()
    assert view.scroll_y == 1
    assert view.convert_distance_to_scroll(0, 30) == (0, 0.1)
    view.do_scroll_y = False
    assert view.convert_distance_to_scroll(0, 30) == (0, 0)


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


def test_claimed_bar_drag_survives_child_touch_flags_and_settles():
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
    # Nested dispatch uses these global keys too. A claimed bar must retain
    # its own axis rather than becoming a content pan when a child writes them.
    touch.ud["in_bar_y"] = False
    touch.ud["in_bar_x"] = False
    touch.dispatch_done()
    touch.move({"x": touch.sx, "y": (view.top - 22) / (Window.height - 1)})
    touch.scale_for_screen(Window.width, Window.height)
    touch.grab_current = view
    view.on_touch_move(touch)
    assert view.scroll_y < 1
    moved = view.scroll_y
    view.on_touch_up(touch)
    for _ in range(5):
        Clock.tick()
    assert view.scroll_y == moved


def test_claimed_horizontal_handle_moves_and_clamps():
    view = DesktopScrollView(size=(300, 200), size_hint=(None, None), do_scroll_y=False)
    view.add_widget(BoxLayout(size=(600, 200), size_hint=(None, None)))
    for _ in range(5):
        Clock.tick()
    view.scroll_x = 0
    touch = UnitTestTouch(view.x + 20, view.y + view.bar_width / 2)
    touch.scale_for_screen(Window.width, Window.height)
    assert view.on_scroll_start(touch)
    touch.ud["in_bar_x"] = False
    touch.dispatch_done()
    touch.move({"x": (view.x + 22) / (Window.width - 1), "y": touch.sy})
    touch.scale_for_screen(Window.width, Window.height)
    touch.grab_current = view
    view.on_touch_move(touch)
    assert 0 < view.scroll_x < 1
    touch.dispatch_done()
    touch.move({"x": (view.right + 200) / (Window.width - 1), "y": touch.sy})
    touch.scale_for_screen(Window.width, Window.height)
    view.on_touch_move(touch)
    assert view.scroll_x == 1
    view.do_scroll_x = False
    touch.dispatch_done()
    touch.move({"x": (view.x + 22) / (Window.width - 1), "y": touch.sy})
    touch.scale_for_screen(Window.width, Window.height)
    view.on_touch_move(touch)
    assert view.scroll_x == 1
    view.on_touch_up(touch)
    for _ in range(5):
        Clock.tick()
    assert view.scroll_x == 1
