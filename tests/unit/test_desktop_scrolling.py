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
