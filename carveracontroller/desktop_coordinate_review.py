"""An explicit snapshot inspector; all coordinate inputs remain local review drafts."""

import time
from datetime import datetime, timezone

from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.addons.machine_simulation.profile import CAD_OFFSET
from carveracontroller.desktop_components import (
    MUTED,
    Action,
    AdaptiveGrid,
    DesktopScrollView,
    QuantityField,
    Surface,
    label,
    release_screen_focus,
)
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.coordinate_review import review_coordinates


def open_coordinate_review(workspace):
    body = Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
    body.add_widget(content_label("Point in program/WCS coordinates · snapshot review only · mm"))
    fields = [QuantityField(text="0 mm", kind="length", minimum=-10000, maximum=10000) for _ in range(3)]
    inputs = AdaptiveGrid(max_cols=3, min_width=160, row_height=76, spacing=dp(6))
    for axis, field in zip("XYZ", fields):
        cell = BoxLayout(orientation="vertical")
        cell.add_widget(label(axis, 12, MUTED, 20))
        cell.add_widget(field)
        inputs.add_widget(cell)
    body.add_widget(inputs)
    note = content_label("")
    body.add_widget(note)
    scroll = DesktopScrollView(do_scroll_x=False)
    rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
    rows.bind(minimum_height=rows.setter("height"))
    scroll.add_widget(rows)
    body.add_widget(scroll)
    popup = Popup(title="Coordinate chain review", content=body, size_hint=(0.86, 0.9))

    def refresh():
        rows.clear_widgets()
        try:
            viewer = workspace.machine.gcode_viewer
            setup = viewer.machine_setup
            profile = viewer.machine_component_profiles.get("workholding", viewer.machine_profile)
            pivot = (
                profile.workholding.get("pivot_mm", profile.workholding.get("cad_translation_mm")) if profile else None
            )
            review = review_coordinates(
                [field.value() for field in fields],
                setup.work_offset_mm,
                setup.stock_origin_mm,
                setup.stock_size_mm,
                setup.stock_rotation_deg,
                pivot,
                viewer.workholding_offset_mm,
                viewer.workholding_rotation_deg,
                viewer.jaw_offset_mm,
                CAD_OFFSET,
                workspace.machine.controller.observed_pose,
                time.monotonic(),
            )
            profile_identity = getattr(profile, "asset_sha256", None) if profile else None
            note.text = (
                f"Captured {datetime.now(timezone.utc).isoformat()} · CAD archive {profile_identity or 'unknown'}\n"
                "Refresh to re-read setup and telemetry. Configured and reported values do not prove measured mounting."
            )
            for row in review:
                point = (
                    "Unknown / not a point"
                    if row.point_mm is None
                    else "  ".join(f"{axis} {value:.4f}" for axis, value in zip("XYZ", row.point_mm)) + " mm"
                )
                rows.add_widget(content_label(f"{row.name}\n{point}\n{row.source}\n{row.relation}"))
        except (ValueError, TypeError) as exc:
            note.text = str(exc)
        scroll.scroll_y = 1

    actions = AdaptiveGrid(max_cols=2, min_width=160, row_height=34, spacing=dp(6))
    actions.add_widget(Action("Refresh snapshot", refresh))
    actions.add_widget(Action("Close", popup.dismiss))
    body.add_widget(actions)
    popup.bind(on_dismiss=lambda *_: release_screen_focus(body))
    popup.coordinate_fields = fields
    popup.coordinate_rows = rows
    popup.refresh_coordinates = refresh
    refresh()
    popup.open()
    return popup
