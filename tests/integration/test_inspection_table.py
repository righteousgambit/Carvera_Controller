import csv
import io
from unittest.mock import Mock

import pytest
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget

from carveracontroller.desktop_inspection_receipts import InspectionReceiptPanel
from carveracontroller.machine.surface_inspection import SurfaceInspectionStore
from tests.integration.conftest import pump_frames
from tests.unit.test_surface_inspection import feature, receipt


@pytest.mark.parametrize("width", (360, 900))
def test_receipt_sort_keyboard_copy_and_stale_identity_are_read_only(kivy_app, tmp_path, monkeypatch, width):
    import carveracontroller.desktop_inspection_receipts as module

    send, copied = Mock(), Mock()
    monkeypatch.setattr(kivy_app.root.controller, "executeCommand", send)
    monkeypatch.setattr(module.Clipboard, "copy", copied)
    store = SurfaceInspectionStore(tmp_path / "inspection.json")
    identity = feature(store)
    for i in range(27):
        receipt(
            store,
            identity,
            4 + (i - 13) / 100,
            source_ref=f"Source-{i:02}",
            kind="raw_trigger" if i == 26 else "compensated_ball_center",
        )
    original = store.path.read_bytes()
    panel = InspectionReceiptPanel()
    panel.size_hint_x = None
    panel.width = dp(width)
    Window.add_widget(panel)
    covering = Popup(title="Cover", content=Widget())
    try:
        panel.toggle()
        panel.show(store.get(identity))
        pump_frames(6)
        selected = panel.selected_id
        stale_action = panel.buttons[-1]
        panel.order.text = "Largest absolute deviation"
        assert panel.selected_id == selected
        assert panel.filtered[-1][1]["deviation_mm"] is None
        assert "largest absolute deviation" in panel.legend.text
        assert panel.select_receipt(identity, panel.filtered[0][0]["id"])
        keyboard = panel.receipt_scroll.keyboard
        assert keyboard is not None and panel.receipt_scroll.focus
        for key, index in (("end", 26), ("home", 0), ("pagedown", 12), ("down", 13), ("pageup", 1), ("up", 0)):
            keyboard.dispatch("on_key_down", (0, key), "", [])
            assert panel.selected_id == panel.filtered[index][0]["id"]
            assert panel.page == index // panel.PAGE_SIZE
        keyboard.dispatch("on_key_down", (0, "c"), "", ["ctrl"])
        exported = list(csv.DictReader(io.StringIO(copied.call_args.args[0]), delimiter="\t"))
        assert len(exported) == 1 and exported[0]["receipt_id"] == panel.selected_id
        assert exported[0]["source_ref"] == panel.filtered[0][0]["source_ref"]
        panel.search.text = "Source-02"
        panel.copy_filtered.dispatch("on_release")
        exported = list(csv.DictReader(io.StringIO(copied.call_args.args[0]), delimiter="\t"))
        assert len(exported) == 1 and exported[0]["source_ref"] == "Source-02"
        chosen = panel.selected_id
        panel.search.focus = True
        assert not panel.receipt_scroll.focus
        panel.search.keyboard.dispatch("on_key_down", (0, "home"), "", [])
        assert panel.selected_id == chosen
        panel.search.focus = False
        stale_action.dispatch("on_release")
        assert panel.selected_id == chosen
        covering.open(animation=False)
        pump_frames(3)
        keyboard.dispatch("on_key_down", (0, "end"), "", [])
        assert panel.selected_id == chosen and not panel.receipt_scroll.focus
        covering.dismiss(animation=False)
        panel.show(None)
        assert panel.copy_filtered.disabled and panel.copy_selected.disabled
        assert not panel.select_receipt(identity, chosen)
        assert store.path.read_bytes() == original
        send.assert_not_called()
    finally:
        covering.dismiss(animation=False)
        panel.receipt_scroll.focus = False
        Window.remove_widget(panel)
        pump_frames(3)


def test_thousand_receipts_keep_bounded_rows_exact_navigation_and_export(kivy_app, tmp_path, monkeypatch):
    import json
    import time

    import carveracontroller.desktop_inspection_receipts as module

    store = SurfaceInspectionStore(tmp_path / "inspection.json")
    identity = feature(store)
    receipt(store, identity, 4.01)
    f = store.get(identity)
    template = f["samples"][0]
    f["samples"] = [
        dict(template, id=f"receipt-{i}", source_ref=f"Source-{i:04}", recorded_at=float(i)) for i in range(1000)
    ]
    copied = Mock()
    monkeypatch.setattr(module.Clipboard, "copy", copied)
    panel = InspectionReceiptPanel()
    Window.add_widget(panel)
    try:
        panel.toggle()
        started = time.monotonic()
        panel.show(f)
        show_s = time.monotonic() - started
        started = time.monotonic()
        panel.order.text = "Newest recorded"
        sort_s = time.monotonic() - started
        pump_frames(4)
        assert len(panel.filtered) == 1000 and len(panel.buttons) <= 12
        panel.move_selection("home")
        assert panel.selected_id == "receipt-999"
        panel.move_selection("end")
        assert panel.selected_id == "receipt-0" and len(panel.buttons) <= 12
        panel.copy_receipts(all_filtered=True)
        rows = list(csv.DictReader(io.StringIO(copied.call_args.args[0]), delimiter="\t"))
        assert len(rows) == 1000 and len({row["receipt_id"] for row in rows}) == 1000
        assert rows[0]["receipt_id"] == "receipt-999" and rows[-1]["receipt_id"] == "receipt-0"
        (tmp_path / "receipt-timing.json").write_text(
            json.dumps(
                {
                    "source_show_s": show_s,
                    "source_sort_s": sort_s,
                    "receipts": 1000,
                    "rendered_rows": len(panel.buttons),
                    "installed_latency": "unverified",
                }
            )
        )
        print(f"1000 receipt source study: show={show_s:.4f}s sort={sort_s:.4f}s rows={len(panel.buttons)}")
    finally:
        Window.remove_widget(panel)
        pump_frames(3)
