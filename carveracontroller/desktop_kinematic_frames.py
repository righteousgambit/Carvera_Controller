"""Read-only snapshot of the explicitly declared tool and workpiece frame chains."""

from datetime import datetime, timezone

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import Action, DesktopScrollView, Surface, release_screen_focus
from carveracontroller.desktop_coordinate_tree import CoordinateTree
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.kinematic_frames import declared_frame_paths


def open_kinematic_frames(record, positions, length, state_source):
    paths = declared_frame_paths(record, dict(positions), length)
    captured = datetime.now(timezone.utc).isoformat()
    body = Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
    body.add_widget(
        content_label(
            f"Declared frame snapshot · {state_source}\nCaptured {captured} · world origins in mm; rotations in details. No machine commands."
        )
    )
    scroll = DesktopScrollView(do_scroll_x=False)
    content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
    content.bind(minimum_height=content.setter("height"))
    scroll.add_widget(content)
    body.add_widget(scroll)
    detail = content_label("")
    content.add_widget(detail)
    rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
    rows.bind(minimum_height=rows.setter("height"))
    content.add_widget(rows)

    def align_detail(_dt):
        if popup.parent is None or content.height <= scroll.height:
            return
        top = scroll.parent.to_widget(*detail.to_window(detail.x, detail.top))[1]
        _, delta = scroll.convert_distance_to_scroll(0, scroll.top - top - dp(8))
        scroll.scroll_y = min(1, max(0, scroll.scroll_y - delta))

    navigate = Clock.create_trigger(lambda _dt: Clock.schedule_once(align_detail, 0), 0)
    tree = CoordinateTree(rows, detail, on_inspect=navigate)
    tree.show_paths(paths, captured)
    popup = Popup(title="Declared joint/frame chain", content=body, size_hint=(0.86, 0.9))
    body.add_widget(Action("Close", popup.dismiss))

    def cleanup(*_):
        navigate.cancel()
        release_screen_focus(body)

    popup.bind(on_dismiss=cleanup)
    popup.frame_tree = tree
    popup.frame_detail = detail
    popup.frame_scroll = scroll
    popup.open()
    return popup
