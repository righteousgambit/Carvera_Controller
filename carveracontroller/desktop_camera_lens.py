"""Transactional, labelled camera intrinsics drafts; no file or machine writes."""

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.desktop_components import (
    MUTED,
    Action,
    AdaptiveGrid,
    DesktopScrollView,
    Field,
    Surface,
    label,
    release_screen_focus,
)
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.camera_registration import CameraIntrinsics


def open_camera_lens(panel):
    reference = panel.reference
    if reference is None:
        panel.note.text = "Capture a reference image before editing its lens model."
        return None
    identity, owner = panel._input_identity(), panel._owner_identity()
    body = Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
    width, height = reference.frame.size
    body.add_widget(content_label(f"{width} × {height} pixels · lens prior"))
    scroll = DesktopScrollView(do_scroll_x=False)
    content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
    content.bind(minimum_height=content.setter("height"))
    scroll.add_widget(content)
    body.add_widget(scroll)
    focal = panel.focal.text.replace(",", " ").split()
    values = focal if len(focal) == 4 else [""] * 4
    values += [str(value) for value in panel.lens_distortion]
    names = (
        ("fx", "Horizontal focal length · pixels"),
        ("fy", "Vertical focal length · pixels"),
        ("cx", "Principal point X · pixels"),
        ("cy", "Principal point Y · pixels"),
        ("k1", "Radial distortion k1"),
        ("k2", "Radial distortion k2"),
        ("p1", "Tangential distortion p1"),
        ("p2", "Tangential distortion p2"),
        ("k3", "Radial distortion k3"),
    )
    fields = {}
    grid = AdaptiveGrid(max_cols=2, min_width=220, row_height=82, spacing=dp(8))
    for (name, title), value in zip(names, values):
        cell = BoxLayout(orientation="vertical", spacing=dp(4))
        cell.add_widget(label(title, 12, MUTED, 30))
        field = Field(text=value)
        fields[name] = field
        cell.add_widget(field)
        grid.add_widget(cell)
    content.add_widget(grid)
    note = content_label(
        "Coefficients are dimensionless. Zero distortion is an assumed model unless measured. "
        "Apply updates this draft; refit and review residuals before saving calibration."
    )
    content.add_widget(note)
    popup = Popup(title="Camera lens model", content=body, size_hint=(0.86, 0.9))

    def apply():
        if panel.running or identity != panel._input_identity() or owner != panel._owner_identity():
            note.text = "Reference, inputs or camera owner changed. Close and reopen the lens editor; no draft applied."
            scroll.scroll_y = 0
            return
        try:
            numbers = [float(fields[name].text.strip()) for name, _ in names]
            intrinsics = CameraIntrinsics(width, height, *numbers[:4], tuple(numbers[4:]))
        except (ValueError, TypeError) as exc:
            note.text = f"Lens draft not applied: {exc}. Enter finite values and positive focal lengths."
            scroll.scroll_y = 0
            return
        panel.lens_distortion = intrinsics.distortion
        panel.focal.text = " ".join(str(value) for value in numbers[:4])
        panel._refresh_review()
        panel.update_overlay()
        panel.note.text = "Lens prior updated locally. Refit and review image residuals before saving calibration."
        popup.dismiss()

    actions = AdaptiveGrid(max_cols=2, min_width=140, row_height=34, spacing=dp(6))
    actions.add_widget(Action("Cancel", popup.dismiss))
    actions.add_widget(Action("Apply lens draft", apply))
    body.add_widget(actions)
    popup.bind(on_dismiss=lambda *_: release_screen_focus(body))
    popup.lens_fields = fields
    popup.lens_note = note
    popup.lens_scroll = scroll
    popup.apply_lens = apply
    popup.open()
    return popup
