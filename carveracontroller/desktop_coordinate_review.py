"""An explicit snapshot inspector; all coordinate inputs remain local review drafts."""

import time
from datetime import datetime, timezone

from kivy.clock import Clock
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.popup import Popup

from carveracontroller.addons.machine_simulation.profile import CAD_OFFSET
from carveracontroller.desktop_components import (
    MUTED,
    Action,
    AdaptiveGrid,
    DesktopScrollView,
    Fold,
    QuantityField,
    Surface,
    label,
    release_screen_focus,
)
from carveracontroller.desktop_coordinate_tree import CoordinateTree
from carveracontroller.desktop_operations import content_label
from carveracontroller.machine.coordinate_review import review_coordinates


def coordinate_snapshot(workspace, point):
    """Read configured geometry and one reported pose without controller writes."""
    viewer = workspace.machine.gcode_viewer
    setup = viewer.machine_setup
    profile = viewer.machine_component_profiles.get("workholding", viewer.machine_profile)
    pivot = profile.workholding.get("pivot_mm", profile.workholding.get("cad_translation_mm")) if profile else None
    review = review_coordinates(
        point,
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
    return review, profile_identity


def open_coordinate_review(workspace, selected_name=None):
    body = Surface(orientation="vertical", padding=dp(12), spacing=dp(8))
    body.add_widget(content_label("Coordinate dependencies · snapshot review · mm"))
    fields = [QuantityField(text="0 mm", kind="length", minimum=-10000, maximum=10000) for _ in range(3)]
    inputs = AdaptiveGrid(max_cols=3, min_width=160, row_height=76, spacing=dp(6))
    for axis, field in zip("XYZ", fields):
        cell = BoxLayout(orientation="vertical")
        cell.add_widget(label(axis, 12, MUTED, 20))
        cell.add_widget(field)
        inputs.add_widget(cell)
    scroll = DesktopScrollView(do_scroll_x=False)
    content = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
    content.bind(minimum_height=content.setter("height"))
    scroll.add_widget(content)
    body.add_widget(scroll)
    point_fold = Fold("Edit review point · program/WCS mm", inputs, body_height=228)
    content.add_widget(point_fold)

    def fit_fold(fold, height):
        fold.body_height = height
        if fold.expanded:
            fold.height = dp(54) + height

    inputs.bind(height=lambda _grid, height: fit_fold(point_fold, height))
    fit_fold(point_fold, inputs.height)
    note = content_label("")
    content.add_widget(note)
    provenance = content_label("")
    provenance_fold = Fold("Snapshot provenance", provenance, body_height=130)
    provenance.bind(height=lambda _label, height: fit_fold(provenance_fold, height))
    content.add_widget(provenance_fold)
    detail = content_label("Select a coordinate path")
    detail_card = Surface(orientation="vertical", padding=dp(8), size_hint_y=None)
    detail_card.bind(minimum_height=detail_card.setter("height"))
    detail_card.add_widget(detail)
    content.add_widget(detail_card)
    rows = BoxLayout(orientation="vertical", size_hint_y=None, spacing=dp(8))
    rows.bind(minimum_height=rows.setter("height"))
    content.add_widget(rows)
    navigate_detail = Clock.create_trigger(lambda _dt: scroll.scroll_to(detail_card, animate=False), 0)
    tree = CoordinateTree(rows, detail, on_inspect=navigate_detail)
    popup = Popup(title="Coordinate chain review", content=body, size_hint=(0.86, 0.9))

    requested_name = selected_name

    def refresh():
        nonlocal requested_name
        try:
            review, profile_identity = coordinate_snapshot(workspace, [field.value() for field in fields])
            captured = datetime.now(timezone.utc).isoformat()
            note.text = (
                "Snapshot review · configured preview and reported packet are separate. Select a path to inspect it."
            )
            provenance.text = (
                f"Captured {captured}\nCAD archive {profile_identity or 'unknown'}\n"
                "Refresh to re-read setup and telemetry. Configured and reported values do not prove measured mounting."
            )
            tree.show(review, captured)
            if requested_name is not None and not tree.select(requested_name, navigate=True):
                note.text = (
                    f"{requested_name} is unavailable in this refreshed snapshot · inspect the current paths below."
                )
            requested_name = None
        except (ValueError, TypeError) as exc:
            note.text = str(exc)
            tree.clear("Cannot review these coordinates · correct the inputs and refresh.")
            provenance.text = "No current coordinate snapshot."
        scroll.scroll_y = 1

    actions = AdaptiveGrid(max_cols=2, min_width=80, row_height=36, spacing=dp(6))
    actions.add_widget(Action("Refresh", refresh))
    actions.add_widget(Action("Close", popup.dismiss))
    body.add_widget(actions)

    def cleanup(*_):
        navigate_detail.cancel()
        release_screen_focus(body)

    popup.bind(on_dismiss=cleanup)
    popup.coordinate_fields = fields
    popup.coordinate_rows = rows
    popup.refresh_coordinates = refresh
    popup.coordinate_tree = tree
    popup.coordinate_detail = detail
    popup.coordinate_scroll = scroll
    popup.coordinate_content = content
    popup.coordinate_point_fold = point_fold
    popup.coordinate_provenance = provenance

    def invalidate(*_):
        tree.clear("Review point changed · refresh for a current coordinate snapshot.")
        provenance.text = "No current coordinate snapshot."
        note.text = "Previous snapshot cleared. Editing is local and sends no controller commands."

    for field in fields:
        field.bind(text=invalidate)
    refresh()
    popup.open()
    return popup
