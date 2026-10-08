"""Read-only snapshot of the explicitly declared tool and workpiece frame chains."""

from datetime import datetime, timezone

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import (
    Action,
    AdaptiveGrid,
    Choice,
    DesktopScrollView,
    Surface,
    release_screen_focus,
)
from carveracontroller.desktop_coordinate_tree import CoordinateTree
from carveracontroller.desktop_frame_diagram import FrameDiagram
from carveracontroller.desktop_operations import content_label
from carveracontroller.desktop_planning import PlanningCard
from carveracontroller.machine.kinematic_frames import declared_frame_paths, declared_spatial_frames


def open_kinematic_frames(record, positions, length, state_source):
    paths = declared_frame_paths(record, dict(positions), length)
    captured = datetime.now(timezone.utc).isoformat()
    spatial = {
        reference: declared_spatial_frames(record, dict(positions), length, reference)
        for reference in ("World", "Workpiece")
    }
    body = Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
    body.add_widget(content_label("Declared geometry · snapshot only · no machine commands"))
    provenance = PlanningCard("Snapshot source & time")
    provenance.content.add_widget(
        content_label(
            f"Declared frame snapshot · {state_source}\nCaptured {captured} · world origins in mm; rotations in details."
        )
    )
    spatial_box = BoxLayout(orientation="vertical", spacing=dp(4), size_hint_y=None, height=0)
    reference = Choice(text="World", values=("World", "Workpiece"))
    view = Choice(text="Isometric", values=("Isometric", "Top", "Front", "Right"))
    controls = AdaptiveGrid(max_cols=2, min_width=80, row_height=32, spacing=dp(4))
    controls.add_widget(reference)
    controls.add_widget(view)
    diagram = FrameDiagram(spatial["World"], size_hint_y=None, height=dp(150))
    caption = content_label("")

    def update_spatial(*_):
        diagram.frames = spatial[reference.text]
        diagram.view = view.text
        diagram.select(tree.selected_name or paths[0].review.name)
        selected = next(frame for frame in diagram.frames if frame.name == diagram.selected_name)
        caption.text = f"{reference.text} reference · {selected.name} · X red / Y green / Z blue. " + (
            "Direction glyph at spindle reference; no tip position."
            if selected.direction_only
            else "Origins in mm; axis glyph lengths for display only."
        )
        caption.text += " Click an origin; arrow keys inspect frames; Home/End reach the chain ends."

    def toggle_spatial():
        if spatial_box.children:
            diagram.focus = False
            spatial_box.clear_widgets()
            spatial_box.height = 0
            spatial_action.text = "Show spatial frame view"
        else:
            for widget in (controls, diagram, caption):
                spatial_box.add_widget(widget)
            spatial_box.height = controls.height + diagram.height + caption.height + dp(8)
            spatial_action.text = "Hide spatial frame view"
            update_spatial()
            navigate()

    spatial_action = Action("Show spatial frame view", toggle_spatial, height=dp(32))
    body.add_widget(spatial_action)
    reference.bind(text=update_spatial)
    view.bind(text=update_spatial)
    caption.bind(
        height=lambda *_: (
            setattr(spatial_box, "height", controls.height + diagram.height + caption.height + dp(8))
            if spatial_box.children
            else None
        )
    )
    scroll = DesktopScrollView(do_scroll_x=False)
    content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
    content.bind(minimum_height=content.setter("height"))
    scroll.add_widget(content)
    body.add_widget(scroll)
    content.add_widget(spatial_box)
    content.add_widget(provenance)
    detail = content_label("")
    content.add_widget(detail)
    rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(6))
    rows.bind(minimum_height=rows.setter("height"))
    content.add_widget(rows)

    def align_detail(_dt):
        if popup.parent is None or content.height <= scroll.height:
            return
        if spatial_box.children:
            scroll.scroll_y = 1
            return
        top = scroll.parent.to_widget(*detail.to_window(detail.x, detail.top))[1]
        _, delta = scroll.convert_distance_to_scroll(0, scroll.top - top - dp(8))
        scroll.scroll_y = min(1, max(0, scroll.scroll_y - delta))

    navigate = Clock.create_trigger(lambda _dt: Clock.schedule_once(align_detail, 0), 0)
    tree = CoordinateTree(rows, detail, on_inspect=navigate, on_select=lambda name: update_spatial())
    diagram.on_pick = lambda name: tree.select(name)
    tree.show_paths(paths, captured)
    popup = Popup(title="Declared joint/frame chain", content=body, size_hint=(0.86, 0.9))

    def fit_spatial(*_):
        diagram.height = min(dp(150), max(dp(25), scroll.height - controls.height - dp(12)))
        if spatial_box.children:
            spatial_box.height = controls.height + diagram.height + caption.height + dp(8)

    popup.bind(size=fit_spatial)
    controls.bind(height=fit_spatial)
    scroll.bind(height=fit_spatial)
    fit_spatial()
    body.add_widget(Action("Close", popup.dismiss))

    def cleanup(*_):
        navigate.cancel()
        release_screen_focus(body)

    popup.bind(on_dismiss=cleanup)
    popup.snapshot_provenance = provenance
    popup.frame_diagram = diagram
    popup.frame_reference = reference
    popup.frame_view = view
    popup.spatial_action = spatial_action
    popup.spatial_box = spatial_box
    popup.spatial_caption = caption
    popup.frame_tree = tree
    popup.frame_detail = detail
    popup.frame_scroll = scroll
    popup.open()
    return popup
