"""Pointer focus and growing reports retain the reading position in draft dialogs."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.tests.common import UnitTestTouch
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView

from carveracontroller.desktop_components import Action, Field
from carveracontroller.desktop_inspection_batch import InspectionBatchDialog
from carveracontroller.desktop_operations import content_label
from carveracontroller.desktop_planning import planning_popup
from carveracontroller.desktop_surface_measurement import SurfaceMeasurementReview
from carveracontroller.machine.scene_interaction import SurfaceHit
from carveracontroller.machine.surface_inspection import SurfaceInspectionStore
from tests.integration.conftest import pump_frames
from tests.unit.test_surface_inspection import feature


@pytest.mark.parametrize("dialog_kind", ("stock", "surface", "batch"))
def test_pointer_focus_then_growing_report_keeps_top_and_resize_preserves_draft(
    kivy_app, tmp_path, monkeypatch, dialog_kind
):
    send = Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    store = None
    if dialog_kind == "stock":
        body = BoxLayout(orientation="vertical", spacing=dp(8))
        field = Field(text="Stock block", size_hint_y=None, height=dp(40))
        report = content_label("Draft dimensions")
        action = Action("Review draft")
        for widget in (field, report, action):
            body.add_widget(widget)
        popup = planning_popup("Stock draft", body)
        popup.open(animation=False)
    elif dialog_kind == "surface":
        hit = SurfaceHit("stock", "stock", 0, 10, (1, 2, 3), (1, 2, 3), (0, 0, 1), ((0, 0, 3), (10, 0, 3), (0, 10, 3)))
        review = SurfaceMeasurementReview(SimpleNamespace(selected_surface=lambda: hit))
        popup, field, report = review.popup, review.part, review.result
        popup.open(animation=False)
    else:
        store = SurfaceInspectionStore(tmp_path / "inspection.json")
        identity = feature(store)
        before = store.path.read_bytes()
        owner = SimpleNamespace(
            choices={"Feature": identity},
            selector=SimpleNamespace(text="Feature"),
            store=store,
            kind=SimpleNamespace(text="Compensated ball center"),
            closed=False,
        )
        review = InspectionBatchDialog(owner)
        popup, field, report = review.popup, review.table, review.note
    try:
        popup.size_hint = (None, None)
        popup.size = (dp(850), min(Window.height * 0.95, dp(1100)))
        pump_frames(15)
        scroll = next(item for item in popup.content.walk() if isinstance(item, ScrollView))
        assert scroll._viewport.height < scroll.height  # Focus the short form before a report arrives.
        scroll.scroll_y = 1
        scroll.scroll_to(field, animate=False)
        pump_frames(5)
        touch = UnitTestTouch(*field.to_window(*field.center))
        touch.touch_down()
        touch.touch_up()
        pump_frames(20, sleep=0.01)
        assert field.focus
        assert scroll.scroll_y == pytest.approx(1), dialog_kind
        draft = "unsubmitted local draft"
        field.text = draft
        report.text = "\n".join(f"Declared report row {index}" for index in range(100))
        pump_frames(15)
        assert scroll._viewport.height > scroll.height
        assert scroll.scroll_y == pytest.approx(1), dialog_kind
        assert field.text == draft
        popup.export_to_png(str(tmp_path / f"{dialog_kind}-expanded-report.png"))
        popup.width = dp(420)
        popup.height = dp(500)
        pump_frames(15)
        scroll.scroll_to(field, animate=False)
        pump_frames(5)
        x, y = field.to_window(*field.center)
        left, bottom = scroll.to_window(scroll.x, scroll.y)
        assert left <= x <= left + scroll.width and bottom <= y <= bottom + scroll.height
        assert field.text == draft
        assert scroll.do_scroll_x is False
        popup.export_to_png(str(tmp_path / f"{dialog_kind}-compact-draft.png"))
        if store is not None:
            assert store.path.read_bytes() == before
        send.assert_not_called()
    finally:
        field.focus = False
        popup.dismiss(animation=False)
        pump_frames(5)
